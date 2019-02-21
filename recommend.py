#!/usr/bin/env python3

import configparser
import flickrapi
import math
import requests

ENVIRONMENT = "prod"

config = configparser.ConfigParser()

config.read("config/config.ini")
config.read("config/secrets.ini")

flickrApiKey                    = config.get(ENVIRONMENT, "flickr.api.key")
flickrApiSecret                 = config.get(ENVIRONMENT, "flickr.api.secret")
flickrApiRetries                = config.getint(ENVIRONMENT, "flickr.api.retries") 
flickrApiMaxFavoritesPerCall    = config.getint(ENVIRONMENT, "flickr.api.favourites.maxpercall")
flickrUserId                    = config.get(ENVIRONMENT, "flickr.user.id")
numResults                      = config.getint(ENVIRONMENT, "results.num")

def getFavorites(flickr, user_id, max_retries, max_per_call):
    numRetries = 0
    favorites = None
    success = False
    error = None

    while numRetries < max_retries:
        try:
            favorites = flickr.favorites.getList(user_id=user_id, extras='url_l,url_m', per_page=max_per_call)
            success = True

        except flickrapi.exceptions.FlickrError as e:
            # You get random 502s when making lots of calls to this API, which apparently indicate rate limiting: 
            # https://www.flickr.com/groups/51035612836@N01/discuss/72157646430151464/ 
            # Sleeping between calls didn't seem to always solve it, but retrying does
            # There doesn't seem to be a way to determine that this happened from the exception object other than to test
            # the string against "do_request: Status code 502 received"
            print("************* Got FlickrError ", e)
            error = e

        except requests.exceptions.ConnectionError as e:
            print("******************* Got ConnectionError: ", e)
            # Sometimes we see a random "Remote end closed connection without response" error
            error = e

        numRetries += 1

    if not success:
        raise error

    return favorites

def getNeighborScore(total_favorites, common_favorites):
    # Took this formula from https://www.flickr.com/groups/709526@N23/discuss/72157604460161681/72157604455830572
    return 150 * math.sqrt(common_favorites / (total_favorites + 250))

flickr = flickrapi.FlickrAPI(flickrApiKey, flickrApiSecret, format='parsed-json', cache=True) # TODO: May want to explore more cacheing options later: https://stuvel.eu/flickrapi-doc/6-caching.html

# To locate photos that the user may find interesting, we first build a set of "neighbors" to this user.
# A "neighbor" is someone who took a photo that the user favorited.
# We will then assign a score to each of these neighbors, and use those scores to assign scores to their favorite photos.
# The highest-scored of these photos will be shown to the original user.

myFavorites = getFavorites(flickr, flickrUserId, flickrApiRetries, flickrApiMaxFavoritesPerCall)
myFavoriteIds = set()
allNeighborFavoritePhotoIds = {}

myNeighbors = {}

for photo in myFavorites['photos']['photo']:
    #print("Found favourite photo ", photo)
    myFavoriteIds.add(photo['id'])
    if photo['owner'] not in myNeighbors:
        myNeighbors[photo['owner']] = { 'userId': photo['owner'] }

#print("***************")
#print("Found neighbors: ", myNeighbors)

# To calculate the score of each neighbour we need to know its favourites

for neighborId in myNeighbors:

    myNeighbors[neighborId]['favoriteIds'] = set()

    print("Looking at neighbor %s" % (myNeighbors[neighborId]['userId']))

    neighborFavorites = getFavorites(flickr, myNeighbors[neighborId]['userId'], flickrApiRetries, flickrApiMaxFavoritesPerCall)

    for photo in neighborFavorites['photos']['photo']:
        #print("Found neighbor favourite photo ", photo)

        myNeighbors[neighborId]['favoriteIds'].add(photo['id'])
        allNeighborFavoritePhotoIds[photo['id']] = { 'score': 0, 'url': photo.get('url_l', photo.get('url_m', '')) }

# Now we can get the total number of favorites for each neighbor, as well as the number of favorites in common with us

for neighborId in myNeighbors:
    myNeighbors[neighborId]['totalFavorites']   = len(myNeighbors[neighborId]['favoriteIds'])   
    myNeighbors[neighborId]['commonFavorites']  = len(myNeighbors[neighborId]['favoriteIds'] & myFavoriteIds)
    myNeighbors[neighborId]['score']            = getNeighborScore(myNeighbors[neighborId]['totalFavorites'], myNeighbors[neighborId]['commonFavorites'])
    print("Neighbor %s has %d total favorites and %d in common with me for a score of %f" % (neighborId, myNeighbors[neighborId]['totalFavorites'], myNeighbors[neighborId]['commonFavorites'], myNeighbors[neighborId]['score']))

# And last we can go through all of our neighbors' favorites and score them
# The score of a photo is the sum of the scores of all the neighbors who favorited it.
# Taken from https://www.flickr.com/groups/709526@N23/discuss/72157604460161681/72157604455830572

for photoId in allNeighborFavoritePhotoIds:
    score = 0
    if photoId not in myFavoriteIds: # Don't recommend photos to me that I already like
        for neighborId in myNeighbors:
            if photoId in myNeighbors[neighborId]['favoriteIds']:
                score += myNeighbors[neighborId]['score']
        allNeighborFavoritePhotoIds[photoId]['score'] = score

sortedNeighborFavoritePhotoIds = sorted(allNeighborFavoritePhotoIds.items(), key=lambda x: x[1]['score'], reverse=True)

# The result is a list of tuples where the first element is the photo ID, and the second element is a dictionary of score and url

for photo in sortedNeighborFavoritePhotoIds[0:numResults]:
    print("<img src=%s/><br/>" % (photo[1]['url']))
