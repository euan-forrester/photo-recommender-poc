#!/usr/bin/env python3

import configparser
import flickrapi
import math
import requests
import argparse
import logging
from django.core.cache import cache
from django.conf import settings

ENVIRONMENT = "prod"

config = configparser.ConfigParser()

config.read("config/config.ini")
config.read("config/secrets.ini")

flickr_api_key                      = config.get(ENVIRONMENT, "flickr.api.key")
flickr_api_secret                   = config.get(ENVIRONMENT, "flickr.api.secret")
flickr_api_retries                  = config.getint(ENVIRONMENT, "flickr.api.retries") 
flickr_api_max_favorites_per_call   = config.getint(ENVIRONMENT, "flickr.api.favorites.maxpercall")
flickr_api_max_favorites_to_get     = config.getint(ENVIRONMENT, "flickr.api.favorites.maxtoget")
flickr_user_id                      = config.get(ENVIRONMENT, "flickr.user.id")
num_photo_results                   = config.getint(ENVIRONMENT, "results.numphotos")
num_neighbour_results               = config.getint(ENVIRONMENT, "results.numneighbours")
memcached_location                  = config.get(ENVIRONMENT, "memcached.location")
memcached_ttl                       = config.getint(ENVIRONMENT, "memcached.ttl")

def make_memcached_key(key, key_prefix, version):
    # Similar to the default key function, except that we translate the key first. The FlickrAPI package
    # uses objects as keys, then calls repr() on it to translate it into a string. This means the string will have 
    # spaces in the name, but memcached won't accept spaces in the key names, so we have to replace those

    translated_key = repr(key).replace(' ', '$')

    return '%s:%s:%s' % (key_prefix, version, translated_key)

settings.configure(CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': memcached_location,
        'KEY_FUNCTION': make_memcached_key,
        'TIMEOUT': memcached_ttl,
    }
})

def get_person_info(flickr, user_id, max_retries):
    num_retries = 0
    person_info = None
    success = False
    error = None

    while (num_retries < max_retries) and not success:
        try:
            person_info = flickr.people.getInfo(user_id=user_id)
            success = True

        except flickrapi.exceptions.FlickrError as e:
            # You get random 502s when making lots of calls to this API, which apparently indicate rate limiting: 
            # https://www.flickr.com/groups/51035612836@N01/discuss/72157646430151464/ 
            # Sleeping between calls didn't seem to always solve it, but retrying does
            # There doesn't seem to be a way to determine that this happened from the exception object other than to test
            # the string against "do_request: Status code 502 received"
            logging.debug("Got FlickrError %s" % (e))
            error = e

        except requests.exceptions.ConnectionError as e:
            logging.debug("Got ConnectionError %s" % (e))
            # Sometimes we see a random "Remote end closed connection without response" error
            error = e

        num_retries += 1

    if not success:
        raise error

    logging.info("Just called get_person_info for user %s" % (user_id))

    return person_info

def get_favorites_page(flickr, user_id, max_retries, max_per_call, page_number):
    num_retries = 0
    favorites = None
    success = False
    error = None

    while (num_retries < max_retries) and not success:
        try:
            favorites = flickr.favorites.getList(user_id=user_id, extras='url_l,url_m', per_page=max_per_call, page=page_number)
            success = True

        except flickrapi.exceptions.FlickrError as e:
            # You get random 502s when making lots of calls to this API, which apparently indicate rate limiting: 
            # https://www.flickr.com/groups/51035612836@N01/discuss/72157646430151464/ 
            # Sleeping between calls didn't seem to always solve it, but retrying does
            # There doesn't seem to be a way to determine that this happened from the exception object other than to test
            # the string against "do_request: Status code 502 received"
            logging.debug("Got FlickrError %s" % (e))
            error = e

        except requests.exceptions.ConnectionError as e:
            logging.debug("Got ConnectionError %s" % (e))
            # Sometimes we see a random "Remote end closed connection without response" error
            error = e

        num_retries += 1

    if not success:
        raise error

    logging.info("Just called get_favorites_page for page %d with max_per_call %d and returning %d faves" % (page_number, max_per_call, len(favorites['photos']['photo'])))

    return favorites

def get_favorites(flickr, user_id, max_retries, max_per_call, max_to_get):
    got_all_favorites = False
    current_page = 1
    favorites = []

    while not got_all_favorites and len(favorites) < max_to_get:
        favorites_subset = get_favorites_page(flickr, user_id, max_retries, max_per_call, current_page)

        if len(favorites_subset['photos']['photo']) > 0: # We can't just check if the number we got back == the number we requested, because frequently we can get back < the number we requested but there's still more available. This is likely due to not having permission to be able to view all of the ones we requested
            favorites.extend(favorites_subset['photos']['photo'])
        else:
            got_all_favorites = True

        current_page += 1

    favorites_up_to_max = favorites[0:max_to_get]

    logging.info("Returning %d favorites which took %d calls" % (len(favorites_up_to_max), current_page - 1))

    return favorites_up_to_max   

def get_neighbor_score(total_favorites, common_favorites):
    # Took this formula from https://www.flickr.com/groups/709526@N23/discuss/72157604460161681/72157604455830572
    return 150 * math.sqrt(common_favorites / (total_favorites + 250))

parser = argparse.ArgumentParser(description="Recommend Flickr photos based on your favoritess")

parser.add_argument("-d", "--debug", action="store_true", dest="debug", default=False, help="Display debug information")
required_arguments = parser.add_argument_group('required arguments')
required_arguments.add_argument("-o", "--output-file", dest="output_filename", type=str, help="HTML file to output", required=True)

args = parser.parse_args()

log_level = logging.INFO
if args.debug:
    log_level = logging.DEBUG

logging.basicConfig(format='%(levelname)s: %(message)s', level=log_level)

flickr = flickrapi.FlickrAPI(flickr_api_key, flickr_api_secret, format='parsed-json', cache=True)
flickr.cache = cache

# To locate photos that the user may find interesting, we first build a set of "neighbors" to this user.
# A "neighbor" is someone who took a photo that the user favorited.
# We will then assign a score to each of these neighbors, and use those scores to assign scores to their favorite photos.
# The highest-scored of these photos will be shown to the original user.

logging.info("Getting my favourites")

my_favorites = get_favorites(flickr, flickr_user_id, flickr_api_retries, flickr_api_max_favorites_per_call, flickr_api_max_favorites_to_get)
my_favorite_ids = set()
all_neighbor_favorite_photo_ids = {}

my_neighbors = {}

for photo in my_favorites:
    logging.debug("Found favourite photo ", photo)
    my_favorite_ids.add(photo['id'])
    if photo['owner'] not in my_neighbors:
        my_neighbors[photo['owner']] = { 'user_id': photo['owner'] }

logging.debug("Found neighbors: ", my_neighbors)

# To calculate the score of each neighbour we need to know its favourites

for neighbor_id in my_neighbors:

    my_neighbors[neighbor_id]['favorite_ids'] = set()

    logging.info("Getting favorites of neighbor %s" % (my_neighbors[neighbor_id]['user_id']))

    neighbor_favorites = get_favorites(flickr, my_neighbors[neighbor_id]['user_id'], flickr_api_retries, flickr_api_max_favorites_per_call, flickr_api_max_favorites_to_get)

    for photo in neighbor_favorites:
        logging.debug("Found neighbor favourite photo ", photo)

        my_neighbors[neighbor_id]['favorite_ids'].add(photo['id'])
        all_neighbor_favorite_photo_ids[photo['id']] = { 'score': 0, 'image_url': photo.get('url_l', photo.get('url_m', '')), 'id': photo['id'], 'user': photo['owner'] }

# Now we can get the total number of favorites for each neighbor, as well as the number of favorites in common with us

for neighbor_id in my_neighbors:
    my_neighbors[neighbor_id]['total_favorites']    = len(my_neighbors[neighbor_id]['favorite_ids'])   
    my_neighbors[neighbor_id]['common_favorites']   = len(my_neighbors[neighbor_id]['favorite_ids'] & my_favorite_ids)
    my_neighbors[neighbor_id]['score']              = get_neighbor_score(my_neighbors[neighbor_id]['total_favorites'], my_neighbors[neighbor_id]['common_favorites'])
    logging.info("Neighbor %s has %d total favorites and %d in common with me for a score of %f" % (neighbor_id, my_neighbors[neighbor_id]['total_favorites'], my_neighbors[neighbor_id]['common_favorites'], my_neighbors[neighbor_id]['score']))

# And last we can go through all of our neighbors' favorites and score them
# The score of a photo is the sum of the scores of all the neighbors who favorited it.
# Taken from https://www.flickr.com/groups/709526@N23/discuss/72157604460161681/72157604455830572

for photoId in all_neighbor_favorite_photo_ids:
    score = 0
    if photoId not in my_favorite_ids: # Don't recommend photos to me that I already like
        for neighbor_id in my_neighbors:
            if photoId in my_neighbors[neighbor_id]['favorite_ids']:
                score += my_neighbors[neighbor_id]['score']
    all_neighbor_favorite_photo_ids[photoId]['score'] = score

sorted_neighbor_favorite_photo_ids = sorted(all_neighbor_favorite_photo_ids.items(), key=lambda x: x[1]['score'], reverse=True)

# The result is a list of tuples where the first element is the photo ID, and the second element is a dictionary of score and url

# Similarly, we sort our neighbors themselves by their score

sorted_neighbors = sorted(my_neighbors.items(), key=lambda x: x[1]['score'], reverse=True)

# Get some info about each of our top users

for neighbor in sorted_neighbors[0:num_neighbour_results]:
    neighbor_info = get_person_info(flickr, neighbor[1]['user_id'], flickr_api_retries)
    neighbor[1]['name'] = neighbor_info['person']['username']['_content']
    neighbor[1]['photostream_url'] = neighbor_info['person']['photosurl']['_content']
    neighbor[1]['favorites_url'] = '%sfavorites' % neighbor[1]['photostream_url']
    
    # Construct a link to their buddy icon according to these rules: https://www.flickr.com/services/api/misc.buddyicons.html
    neighbor[1]['buddy_icon'] = 'https://www.flickr.com/images/buddyicon.gif'

    icon_server = int(neighbor_info['person']['iconserver'])
    if icon_server > 0:
        neighbor[1]['buddy_icon'] = 'http://farm%d.staticflickr.com/%d/buddyicons/%s.jpg' % (neighbor_info['person']['iconfarm'], icon_server, neighbor_info['person']['nsid'])
    
# Write out our final file

f = open(args.output_filename, "w+")

f.write("<h1>Photos you may like</h1>\n")

for photo in sorted_neighbor_favorite_photo_ids[0:num_photo_results]:
    f.write("<a href=https://www.flickr.com/photos/%s/%s/><img src=%s/></a><br/>\n" % (photo[1]['user'], photo[1]['id'], photo[1]['image_url']))

f.write("<h1>Other users you may like</h1>\n")

for neighbor in sorted_neighbors[0:num_neighbour_results]:
    f.write("<img src=%s/>%s - <a href=%s>Photos</a> - <a href=%s>Favorites</a><br/>\n" % (neighbor[1]['buddy_icon'], neighbor[1]['name'], neighbor[1]['photostream_url'], neighbor[1]['favorites_url']))

f.close()

logging.info("Finished writing output file %s" % (args.output_filename))