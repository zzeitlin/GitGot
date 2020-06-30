
![Python version](https://img.shields.io/badge/python-3.x-blue.svg)

## Description

Inquisitor is a multi-threaded GitHub query engine that ingests large lists of sensitive queries, and outputs query results for parsing. It empowers users by providing a queue that feeds into GitHub's API. If you have thousands of queries to perform but not the time to do it, add it to the queue and let Inquisitor churn.

### How it Works

Input + Augmentor + Parameters = Query


## Install Instructions
GitHub requires a token for rate-limiting purposes. Create a [GitHub API token](https://github.com/settings/tokens) with **no permissions/no scope**. This will be equivalent to public GitHub access, but it will allow access to use the GitHub Search API.

```bash
# Install the source
   $ git clone
   $ python3 -m venv .env
   $ source .env/bin/activate
   $ python3 -m pip install -r requirements.txt

# Add one (or many) GitHub API Tokens. Note that adding numerous tokens from the same account, a per-account rate-limit is enforced by GitHub.
# Note that .gitignore is set to ignore this tokenfile.
   $ echo mygithubapitokengoeshere >> config/tokenfile

# Update configuration
   $ vim config/config.yml
```

### Installation with FireProx
Using [FireProx](https://github.com/ustayready/fireprox) allows you to proxy your source IP address for every query. It is helpful when IP-based API rate limits inhibit query results.
- Create AWS IAM user with `AmazonAPIGatewayAdministrator` policy attached
- Configure the AWS profile on the machine that will execute Inquisitor
  - `aws2 configure --profile fireprox`
- Use fireprox to create a proxy to github's API endpoint:
  - `./fire.py --profile_name fireprox --command create --url https://api.github.com/`
- Update config.yml in Inquisitor and input the generated URL
  - `base_url: https://xxxxxxxx.execute-api.us-east-1.amazonaws.com/fireprox/`

## Usage

### Query Syntax

Inquisitor queries are fed directly into the GitHub code search API, so check out [GitHub's documentation](https://help.github.com/en/articles/searching-code) for more advanced query syntax.
