#!/usr/bin/env python3

import configparser
import flickrapi

ENVIRONMENT = "prod"

config = configparser.ConfigParser()

config.read("config/config.ini")
config.read("config/secrets.ini")

flickrApiKey = config[ENVIRONMENT]["flickr.api.key"]
flickrApiSecret = config[ENVIRONMENT]["flickr.api.secret"]
flickrUserId = config[ENVIRONMENT]["flickr.user.id"]

flickr = flickrapi.FlickrAPI(flickrApiKey, flickrApiSecret, format='parsed-json', cache=True)
sets   = flickr.photosets.getList(user_id=flickrUserId)
title  = sets['photosets']['photoset'][0]['title']['_content']

print("Title of first set: %s" % (title))