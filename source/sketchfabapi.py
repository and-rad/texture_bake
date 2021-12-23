
import json
import os

from time import sleep

# import the requests library
# http://docs.python-requests.org/en/latest
# pip install requests
import requests
from . import functions

##
# Uploading a model to Sketchfab is a two step process
#
# 1. Upload a model. If the upload is successful, the API will return
#    the model's uid in the `Location` header, and the model will be placed in the processing queue
#
# 2. Poll for the processing status
#    You can use your model id (see 1.) to poll the model processing status
#    The processing status can be one of the following:
#    - PENDING: the model is in the processing queue
#    - PROCESSING: the model is being processed
#    - SUCCESSED: the model has being sucessfully processed and can be view on sketchfab.com
#    - FAILED: the processing has failed. An error message detailing the reason for the failure
#              will be returned with the response
#
# HINTS
# - limit the rate at which you poll for the status (once every few seconds is more than enough)
##

SKETCHFAB_DOMAIN = 'sketchfab.com'
SKETCHFAB_API_URL = 'https://api.{}/v3'.format(SKETCHFAB_DOMAIN)


def _get_request_payload(apikey, data={}, files={}, json_payload=False):
    """Helper method that returns the authentication token and proper content
    type depending on whether or not we use JSON payload."""
    headers = {'Authorization': 'Token {}'.format(apikey)}

    if json_payload:
        headers.update({'Content-Type': 'application/json'})
        data = json.dumps(data)

    return {'data': data, 'files': files, 'headers': headers}


def upload(model_file, uploadname, apikey):
    """POST a model to sketchfab.

    This endpoint only accepts formData as we upload a file.
    """
    #model_endpoint = os.path.join(SKETCHFAB_API_URL, 'models')
    
    model_endpoint = SKETCHFAB_API_URL + '/models'
    
    functions.printmsg(f"Sketchfab URL is going to be: {model_endpoint}")

    # Optional parameters
    name = uploadname
    description = 'Uploaded with SimpleBake for Blender 2.8'
    #password = 'my-password'  # requires a pro account
    #private = 1  # requires a pro account
    #tags = ['bob', 'character', 'video-games']  # Array of tags
    #categories = ['people']  # Array of categories slugs
    #license = 'CC Attribution'  # License label
    isPublished = False, # Model will be on draft instead of published
    #isInspectable = True, # Allow 2D view in model inspector

    data = {
        'name': name,
        'description': description,
        #'tags': tags,
        #'categories': categories,
        #'license': license,
        #'private': private,
        #'password': password,
        'isPublished': isPublished,
        'source': "simplebake-for-blender"
        #'isInspectable': isInspectable
    }

    f = open(model_file, 'rb')

    files = {'modelFile': f}

    try:
        r = requests.post(
            model_endpoint, **_get_request_payload(apikey,
                data, files=files))
    except requests.exceptions.RequestException as e:
        functions.printmsg('An error occured: {}'.format(e))
        return False
    finally:
        f.close()
    
    functions.printmsg(f"Status code from Sketchfab was {r.status_code}");
    
    if r.status_code != requests.codes.created:
        functions.printmsg('Upload failed with error: {}'.format(r.json()))
        return False

    # Should be https://api.sketchfab.com/v3/models/XXXX
    model_url = r.headers['Location']
    
    #For some reason this is wrong. Correct it here.
    return model_url.replace("https://api.sketchfab.com/v3/models/", "https://sketchfab.com/3d-models/")


