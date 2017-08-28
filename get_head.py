#!/usr/local/bin/python3

import requests
import argparse
import getpass
import json
import pprint
import subprocess
import os

def main():
  pp = pprint.PrettyPrinter(indent=4)
  # Arguments.
  parser = argparse.ArgumentParser(description="Get the hash of HEAD for a branch of a repo on GitHub")
  parser.add_argument('repo', help="Name of the repo to get the HEAD hash for")
  parser.add_argument('--api-url', help="URL of the REST API to request. Defaults to https://api.github.com", default="https://api.github.com")
  parser.add_argument('--creds', help="Path to a file containing a JSON object with 'username' and 'password'. If the file is not found, will fall back to asking for credentials.", default="~/.github_creds")
  parser.add_argument('--owner', help="Owner of the repo. Defaults to discoverygarden.", default="discoverygarden")
  parser.add_argument('--branch', help="Name of the branch to get HEAD hash for. Defaults to the default branch.", default=None)
  parser.add_argument('-c', '--clipboard', help="Flag to copy the hash to the clipboard.", action="store_true")
  args = vars(parser.parse_args())

  creds = {}
  # Get the credentials. Check creds file first.
  try:
    with open(os.path.expanduser(args['creds']), 'r') as f:
      creds_file = f.read()
      creds_file = json.loads(creds_file)
      if 'username' in creds_file:
        creds['username'] = creds_file['username']
      if 'password' in creds_file:
        creds['password'] = creds_file['password']
  except IOError:
    print("Couldn't load credentials at %s; manual input required." % (args['creds']))
  except ValueError:
    print("Invalid JSON in %s; manual input required." % (args['creds']))

  if 'username' not in creds:
    creds['username'] = input('Username: ')
  if 'password' not in creds:
    creds['password'] = getpass.getpass()

  auth = (creds['username'], creds['password'])

  # Check creds and that we have a connection.
  print("Checking connection and credentials ...")
  r = requests.get(args['api_url'], auth=auth)
  if r.status_code == 401:
    print("Failed to authorize")
    exit(1)
  if r.status_code != 200:
    print("Could not connect to %s" % (args['api_url']))
    exit(1)

  if not args['branch']:
    print("Getting default branch ...")
    r = requests.get("%s/repos/%s/%s" % (args['api_url'], args['owner'], args['repo']), auth=auth)
    if r.status_code != 200:
        print("Failed to get information about the requested repo: error %s" % (str(r.status_code)))
        exit(1)
    repo = json.loads(r.text)
    args['branch'] = repo['default_branch']

  r = requests.get("%s/repos/%s/%s/branches/%s" % (args['api_url'], args['owner'], args['repo'], args['branch']), auth=auth)
  if r.status_code != 200:
    print("Couldn't get info for repo branch %s: error %s" % (args['branch'], str(r.status_code)))
    exit(1)
  branch = json.loads(r.text)
  print("%s/%s:%s HEAD: %s" % (args['owner'], args['repo'], args['branch'], branch['commit']['sha']))
  if args['clipboard']:
    process = subprocess.Popen('pbcopy', env={'LANG': 'en_US.UTF-8'}, stdin=subprocess.PIPE)
    process.communicate(branch['commit']['sha'].encode('utf-8'))
    print("Copied to clipboard.")


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print("\nExiting ...")
