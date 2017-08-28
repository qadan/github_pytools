#!/usr/local/bin/python3

from git import Repo;
from sys import exit
from shutil import rmtree
from time import sleep
import os
import requests
import argparse
import getpass
import json

'''
  Accepts a message (no whitespace at the end) so a yes or no question can be
  asked.
'''
def yes_or_no(message):
  valid = {
      "yes": True,
      "ye": True,
      "y": True,
      "no": False,
      "n": False,
      }
  while True:
    choice = input(message + " [Y/n] ").lower()
    if choice == '':
      return True
    elif choice in valid:
      return valid[choice]
    else:
      print("Please respond with 'y' or 'n'")

def main():
  # Arguments.
  parser = argparse.ArgumentParser (description="Delete your fork, of an environment, re-fork, and clone")
  parser.add_argument('repo', help="Name of the repository to delete and clone")
  parser.add_argument('--creds', help="Path to a file containing a JSON object with 'username' and 'password'. If the file is not found, will fall back to asking for credentials.", default="~/.github_creds")
  parser.add_argument('--branch', help="Name of a branch to create on the new fork. Defaults to the default branch of the base repository.", default=None)
  parser.add_argument('--base', help="Name of the base username. Defaults to 'discoverygarden'.", default="discoverygarden")
  parser.add_argument('--api-url', help="URL of the REST API to request. Defaults to https://api.github.com", default="https://api.github.com")
  parser.add_argument('--clone-url', help="URL to clone from. Defaults to ssh://git@github.com", default="ssh://git@github.com")
  parser.add_argument('--dest', help="The destination to clone to. Will default to the working directory (currently %s)" % (os.getcwd()), default=os.getcwd())
  parser.add_argument('-y', help="Answers 'Y' to all script questions", action="store_true")
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
  # Check creds and see that we have a connection.
  print("Checking connection and credentials ...")
  r = requests.get(args['api_url'], auth=auth)
  if r.status_code == 401:
    raise requests.exceptions.RequestException("Failed to authorize")
  if r.status_code != 200:
    raise requests.exceptions.RequestException('Could not connect to %s' % (args['api_url']))

  # Get the fork for its juicy info.
  print("Confirming that re-forking can be done ...")
  r = requests.get("%s/repos/%s/%s" % (args['api_url'], creds['username'], args['repo']), auth=auth)
  if (r.status_code != 200 and r.status_code != 404):
    print("Could not get repo %s; recieved error %s" % (args['repo'], str(r.status_code)))
    return;

  if r.status_code != 404:
    repo = json.loads(r.text)

    # Bail if things are bad.
    if repo['owner']['login'] != creds['username']:
      print("This repository is not owned by you. Exiting ...")
      exit(1)
    if not repo['fork']:
      print("This repository is not a fork. Exiting ...")
      exit(1)
    data = {
      'state': 'open',
    }
    r = requests.get('%s/repos/%s/%s/pulls' % (args['api_url'], repo['parent']['owner']['login'], args['repo']), data=json.dumps(data), auth=auth)
    if r.status_code == 200:
      pulls = json.loads(r.text)
      for pull in pulls:
        if pull['head']['user']['login'] == creds['username']:
          print("You have an existing pull request to the parent (%s). Exiting ..." % (pull['html_url']))
          exit(1)
    else:
      print("Unable to load parent repository. Exiting ...")
      exit(1)

    # Confirm deletion.
    queue_deletion = True
    question_message = "Delete, re-fork and clone %s?" % (repo['full_name'])
    print("Repo found.")

  else:
    queue_deletion = False
    question_message = "No fork could be found. Attempt to fork and clone %s?" % (args['repo'])

  proceed = args['y'] or yes_or_no(question_message)
  if proceed:
    if queue_deletion:
      # Do the deletion.
      print("Deleting %s..." % (repo['full_name']))
      r = requests.delete("%s/repos/%s/%s" % (args['api_url'], creds['username'], args['repo']), auth=auth)
      if r.status_code != 204:
        raise requests.exceptions.RequestException("Failed to delete repo %s; code %s" % (args['repo'], str(r.status_code)))
      print("Successfully deleted")

    # Do the forking.
    print("Forking %s to %s..." % (args['repo'], creds['username']))
    r = requests.post('%s/repos/%s/%s/forks' % (args['api_url'], args['base'], args['repo']), auth=auth)
    if r.status_code != 202:
      raise requests.exceptions.RequestException("Failed to fork %s to %s; code %s" % (args['repo'], creds['username'], str(r.status_code)))
    r = requests.get("%s/repos/%s/%s" % (args['api_url'], creds['username'], args['repo']), auth=auth)
    if r.status_code != 200:
      print("Could not get repo %s; recieved error %s" % (args['repo'], str(r.status_code)))
      return;
    repo = json.loads(r.text)
    print("Successfully forked")

    # Create the new branch.
    if args['branch'] is not None:
      print("Generating branch %s on the new fork." % args['branch'])
      r = requests.get('%s/repos/%s/%s/branches/%s' % (args['api_url'], creds['username'], args['repo'], repo['default_branch']), auth=auth)
      if r.status_code != 200:
        print("Failed to get reference for branch %s on new fork; this will have to be done manually." % args['branch'])
      else:
        branch = json.loads(r.text)
        data = {
          'ref': 'refs/heads/%s' % args['branch'],
          'sha': branch['commit']['sha'],
        }
        r = requests.post('%s/repos/%s/%s/git/refs' % (args['api_url'], creds['username'], args['repo']), auth=auth, data=json.dumps(data))
        if r.status_code != 201:
          print("Failed to create the reference for branch %s on new fork; this will have to be done manually." % args['branch'])

    # Do the cloning.
    clone = args['y'] or yes_or_no("Clone to %s? If the directory exists, it will be deleted." % (args['dest']))
    if clone:
      print("Cloning %s..." % (repo['full_name']))
      destination = '%s/%s' % (args['dest'], args['repo'])
      if not os.path.exists(destination):
        os.makedirs(destination)
      else:
        rmtree(destination)
      retries = 0
      while retries < 5:
        try:
          clone = Repo.clone_from("%s/%s/%s.git" % (args['clone_url'], creds['username'], args['repo']), "%s/%s" % (args['dest'], args['repo']))
          print("Cloned to %s" % (clone.working_dir))
          retries = 5
        except GitCommandError as e:
          retries += 1
          sleep(1)
          if retries == 5:
              print("Failed to clone %s%s%s.git after 5 tries; check to see if the fork has been created and then clone manually." % (args['clone_url'], creds['username'], args['repo']))
      exit(0)

if __name__ == "__main__":
  try:
    main()
  except requests.exceptions.RequestException as e:
    print(e.response)

