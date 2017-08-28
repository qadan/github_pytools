#!/usr/local/bin/python3

from time import sleep
import requests
import argparse
import getpass
import json
import os

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
  current_env = os.getcwd().split('/')[-1]
  # Arguments.
  parser = argparse.ArgumentParser(description="Update an environment on GitHub")
  parser.add_argument('env', help="Name of the environment to update. Defaults to the name of the directory the command is called from (currently %s)." % (current_env), nargs='?', default=current_env)
  parser.add_argument('--api-url', help="URL of the REST API to request. Defaults to https://api.github.com", default="https://api.github.com")
  parser.add_argument('--creds', help="Path to a file containing a JSON object with 'username' and 'password'. If the file is not found, will fall back to asking for credentials.", default="~/.github_creds")
  parser.add_argument('--head-branch', help="Name of the branch changes exist in on your fork. Defaults to 'dev'", default="dev")
  parser.add_argument('--base-branch', help="Name of a branch to pull against. Use multiple to create more than one pull. Defaults to 'dev' and 'qa'", nargs='*', default=[])
  args = vars(parser.parse_args())

  # Just some weirdness to make sure you can do one or the other or more or
  # different ones.
  if not args['base_branch']:
    args['base_branch'] = ['dev', 'qa']

  # The environment should always start with env_ or mod_; skipping a repo name
  # check here to avoid contributing to the rate limiter.
  if not args['env'].startswith('env_') and not args['env'].startswith('mod_'):
    print("%s does not appear to be a valid environment name" % (args['env']))
    exit(1)

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

  # Get the most recent message on the branch as the default title.
  r = requests.get('%s/repos/%s/%s/branches/%s' % (args['api_url'], creds['username'], args['env'], args['head_branch']), auth=auth)
  head_branch = json.loads(r.text)
  title_default = head_branch['commit']['commit']['message']
  message_default = ""

  # Iterate through the branches merging was requested in.
  for branch in args['base_branch']:
    print("Pulling against %s..." % (branch))
    title_default = input("Custom title? (Will default to '{}') ".format(title_default)) or title_default
    message_default = input("Custom message? (Will default to '{}') ".format(message_default)) or message_default
    data = {
      "title": title_default,
      "message": message_default,
      "head": "%s:%s" % (creds['username'], args['head_branch']),
      "base": branch
    }

    # Make the pull.
    r = requests.post('%s/repos/discoverygarden/%s/pulls' % (args['api_url'], args['env']), data=json.dumps(data), auth=auth)
    pull = json.loads(r.text)
    if r.status_code != 201:
      print("Failed to create pull request against %s: error %s (%s). Skipping..." % (branch, str(r.status_code), pull['message']))
      continue
    print("Created %s" % (pull['html_url']))

    # It's a near-guarantee that the mergeable state of the pull will not have
    # been determined at this point; it's easier to just wait a moment here than
    # force retrying the check for every single pull.
    sleep(2)

    # Get the details of the pull for a spot check.
    r = requests.get('%s/repos/discoverygarden/%s/pulls/%s' % (args['api_url'], args['env'], str(pull['number'])), auth=auth)
    pull = json.loads(r.text)

    r = requests.get('%s/repos/discoverygarden/%s/pulls/%s/commits' % (args['api_url'], args['env'], str(pull['number'])), auth=auth)
    commits = json.loads(r.text)
    print("Commits ------- %s" % (str(pull['commits'])))
    for commit in commits:
      print("  %s (%s, %s)" % (commit['commit']['message'], commit['commit']['committer']['name'], commit['commit']['committer']['date']))
      print("(+) ----------- %s" % (str(pull['additions'])))
      print("(-) ----------- %s" % (str(pull['deletions'])))
      print("Changed Files - %s" % (str(pull['changed_files'])))

    if not pull['mergeable']:
      while pull['mergeable_state'] == 'unknown':
        retry = yes_or_no("The mergeable state of the pull request is currently unknown. This may mean that GitHub is still determining whether or not it can be merged. Check again?")
        if retry:
          r = requests.get('%s/repos/discoverygarden/%s/pulls/%s' % (args['api_url'], args['env'], str(pull['number'])), auth=auth)
          pull = json.loads(r.text)
        else:
          break

      if not pull['mergeable']:
        print("The pull request cannot be merged (state: %s). Resolve any conflicts and head to the above URL to manually merge." % (pull['mergeable_state']))
        continue

    # Request to merge, then merge.
    merge = yes_or_no("Mergeable state: %s. Should this be merged?" % (pull['mergeable_state']))
    if merge:
      data = {
        "sha": pull['head']['sha']
      }
      r = requests.put('%s/repos/discoverygarden/%s/pulls/%s/merge' % (args['api_url'], args['env'], str(pull['number'])), data=json.dumps(data), auth=auth)
      response = json.loads(r.text)
      print("Response status: %s (%s)" % (str(r.status_code), response['message']))

if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print("\nExiting ...")
    exit()
