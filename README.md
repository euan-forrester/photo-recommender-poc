# photo-recommender-poc

Proof of concept for a system that recommends photos based on previous photos you liked

# Instructions

## Step 1

First make sure you have python and some packages installed

```
brew install python
brew install memcached
pip3 install flickrapi
pip3 install python-memcached
pip3 install django
```

(The flickrapi package can use the django cacheing interface. So even though it means including the 
entire django package, it seemed easier to use that than to write my own wrapper around memcached that has the
interface the flickrapi package wants)

## Step 2

Copy `config/secrets.ini.example` to the new file `config/secrets.ini`

Edit `config/config.ini` and `config/secrets.ini` to contain your Flickr API key and secret

And in `config/config.ini` you can replace the Flickr user ID with your own. To get your numerical Flickr user ID, you may need to visit: http://idgettr.com/

## Step 3

Run memcache locally. On my Mac there's an instance of it running already, but the memory limit is quite low at 64MB
which isn't big enough to store all of the calls made when the script runs for my user. So this starts a second 
instance on a different port with a larger memory limit.

```
/usr/local/opt/memcached/bin/memcached --memory-limit=512 --port=11212
```

(or whatever `brew` told you to run in step 1 when you did `brew install memcached`)

## Step 4

Run the script

```
./recommend.py -o output/test.html
```

## Step 5

Open the output file in a web browser and enjoy some photos