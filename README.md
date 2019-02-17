# GitHub merger
A serverless automatic GitHub pull request merger.

This script will utilize GitHub webhooks, AWS lambda and GitHub API to automatically merge approved and tested pull requests.
Setting this up should not take more than 10 minutes, given you have the required access to Github and AWS.

## The pain
Does this seem familiar?
1. You create a Pull Request.
2. A peer reviews your code, and finally approves your changes. Gives you a green light to merge (we call this Merge When Green, MWG).
3. Build has not yet completed. As you wouldn't want to break it by mistake, you keep refreshing and waiting for certain Slack notifications about its completion.


## Our solution
1. Use GitHub Review feature for approving pull requests.
2. Get status notifications from build systems (Jenkins, Travis CI, Circle CI and similar).
3. Use GitHub API to automatically merge the pull request.


## Setup
1. Setup a GitHub user for automatically merging pull requests.
    * This user will need write access to your GitHub repository.
    * Yes, we hate this too.
2. [Generate an access token](https://github.com/settings/tokens)
    * Select `repo.*` as access permissions (including `status`, `deployment` and `public_repo`).
3. Create a new AWS lambda function
    * Template: Blank Function
    * Triggers:
        1. Integration: `API gateway`
        2. API name: `GithubMerger`
        3. Deployment stage: `prod`
        4. Security: `open`
    * Configuration:
        1. Name: `github-merger-function`
        2. Runtime: `Python 2.7`
        3. Code entry type: `Upload a ZIP file`. Use the ZIP file in our Releases page, or create your own.
        4. Environment variables:
            * This is where you configure your function (see Configuration section ahead).
            * I recommend you set `GITHUB_TOKEN` and `ALLOWED_REPOS` configuration keys now.
        5. Lambda function:
            * Handler: func.git_review_handler
            * Role: (choose an existing role) -> `lambda_basic_execution`
        6. Advanced settings:
            * Memory: 128MB
            * Timeout `6 seconds`
4. API gateway configuration
    * You're now in your AWS lambda triggers pane.
    * We only need to support POST requests (default is ANY).
        * Click ANY.
        * Under the Resources pane on the left, select ANY. Using the Actions menu, Delete the method.
        * Create a new method (Actions -> Create Method) that will link to your Lambda function.
            * Use Lambda Proxy integration.
        * Deploy the changes: Actions -> Deploy API.
    * Get the URL by going to `"Stages" -> prod -> POST` and copying the `Invoke URL`.
5. GitHub Webhook
    * This can be done on a per-repository or per-account basis. Your call.
    * Under the account or repository settings, go to Settings -> Webhooks.
    * Add a Webhook:
        * Payload URL is the Invoke URL you just copied.
        * Content Type: application/json
        * Events:
            * `Check suites` - This will allow our Lambda function to merge when the build is complete (if it was reviewed before).
            * `Pull request reviews` - The Lambda function will merge when a review completed after the build is completed.
            * `Statuses` - This will use old statuses API for merge triggering - use for API before v3, when check suites was introduced.
6. Go back to writing code.


## Configuration
All these should be set as AWS lambda environment variables.

Setting | Required | Meaning
------- | -------- | -------
ALLOWED_REPOS | Yes | A comma-separated list of github repositories the script is allowed to be executed on (use `*` for everything).
GITHUB_TOKEN | Yes | The GitHub API token you obtained in setup 2 of Setup.
REQUIRED_CONTEXT | No | The source of a required build (default: `continuous-integration/travis-ci/pr`)
GITHUB_SECRET | No | A secret configured in the GitHub webhook configuration. If configured, incoming requests will be validated using it.
TITLE_INDICATOR | No | An indicator within the Pull Request's title to *allow* automatic merging. Default: `[AM]` (case insensitive). Use * to allow everything.
TITLE_PREVENTOR | No | An indicator within the Pull Request's title to *block* automatic merging. Default: `[DM]` (case insensitive). Set to an empty string to allow everything.

## Contributing
We encourage everyone to join in and contribute to this project.
Feel free to open a Pull Request!

## License
This project is licensed under the MIT license.
