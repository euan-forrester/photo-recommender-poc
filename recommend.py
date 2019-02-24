#!/usr/bin/env python3

import configparser
from flickrapiwrapper import FlickrApiWrapper
import math
import argparse
import logging

ENVIRONMENT = "prod"

def get_neighbor_score(total_favorites, common_favorites):
    # Took this formula from https://www.flickr.com/groups/709526@N23/discuss/72157604460161681/72157604455830572
    return 150 * math.sqrt(common_favorites / (total_favorites + 250))

# Read in commandline arguments

parser = argparse.ArgumentParser(description="Recommend Flickr photos based on your favorites")

parser.add_argument("-d", "--debug", action="store_true", dest="debug", default=False, help="Display debug information")
required_arguments = parser.add_argument_group('required arguments')
required_arguments.add_argument("-o", "--output-file", dest="output_filename", type=str, help="HTML file to output", required=True)

args = parser.parse_args()

log_level = logging.INFO
if args.debug:
    log_level = logging.DEBUG

logging.basicConfig(format='%(levelname)s: %(message)s', level=log_level)

# Read in config

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

flickrapi = FlickrApiWrapper(flickr_api_key, flickr_api_secret, memcached_location, memcached_ttl, flickr_api_retries)

# To locate photos that the user may find interesting, we first build a set of "neighbors" to this user.
# A "neighbor" is someone who took a photo that the user favorited.
# We will then assign a score to each of these neighbors, and use those scores to assign scores to their favorite photos.
# The highest-scored of these photos will be shown to the original user.

logging.info("Getting my favourites")

my_favorites = flickrapi.get_favorites(flickr_user_id, flickr_api_max_favorites_per_call, flickr_api_max_favorites_to_get)
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

    neighbor_favorites = flickrapi.get_favorites(my_neighbors[neighbor_id]['user_id'], flickr_api_max_favorites_per_call, flickr_api_max_favorites_to_get)

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
    neighbor_info = flickrapi.get_person_info(neighbor[1]['user_id'])
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
