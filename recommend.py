#!/usr/bin/env python3

import configparser

ENVIRONMENT = "prod"

config = configparser.ConfigParser()

config.read("config/config.ini")
config.read("config/secrets.ini")

print(config[ENVIRONMENT]["flickr.api.key"])
print(config[ENVIRONMENT]["flickr.api.secret"])