# photo-recommender-poc

Proof of concept for a system that recommends photos based on previous photos you liked

# Introduction

This is based off a system called Flexplore written by Lars Pohlmann back around 2008: https://www.flickr.com/groups/flexplore/ 

This script is based off his public posts about how it worked, in particular https://www.flickr.com/groups/709526@N23/discuss/72157604460161681/72157604455830572

The idea behind Flexplore was to function as a better version of Flickr's Explore feature, which purports to help users discover high-quality work from around Flickr. Where Explore scored photos globally based on what Flickr calls "Interestingness", Flexplore tailored its output to each user specifically. The intuition behind its operation was that if I like a photo taken by someone, I will probably like other photos they took. But, it's really *their* favorite photos by other people that demonstrate what they're trying to accomplish. So, if I like one of their photos, I'll probably *really* like what they're shooting for. 

Thus, Flexplore scored the people who took the photos I like by how many favorites we have in common (a proxy for how similar our tastes are). Then it scored the photos *they* like by the other people who favorited them, and shows me the top-scoring photos which are thus defined by my own idiosyncratic tastes.

It was pretty successful at showing people work that was interesting to them that they hadn't seen before: https://www.flickr.com/groups/94761711@N00/discuss/72157604058004797/

Lars later added a feature for "show my more photos like this" that finds photos with similar people who favorited them: https://www.flickr.com/groups/flexplore/discuss/72157630056207294/

I wrote this to see if I could get the general idea working before I took a run at trying to build a scalable system suitable for many users.

I also noticed that it's pretty trivial to generate a list of top-scoring users, and I found in my personal experience that I enjoyed both their work and their favorites, so I included that in the output as well.

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
