# brevio-core-assist (optional)

An optional plugin for brevio-core. It explains a finding, or suggests a fix for it, by asking a model endpoint
that you choose and pay for, with your own key.

It is a separate package. brevio-core does not depend on it and never imports it, and the core's tests check that.
Without this plugin, brevio-core calls no model and needs no key.

## Off until you turn it on

It does nothing until it is installed and these are set:

| Variable | What it holds |
|---|---|
| `BREVIO_ASSIST_URL` | The full URL of your endpoint. It must use https; plain http is allowed only to this machine. |
| `BREVIO_ASSIST_FORMAT` | `chat` for an endpoint that takes a chat-completions request, `messages` for one that takes a messages request. |
| `BREVIO_ASSIST_MODEL` | The model name your endpoint expects. |
| `BREVIO_ASSIST_KEY_ENV` | The name of the variable that holds your key, for example `MY_ENDPOINT_KEY`. |
| `BREVIO_ASSIST_HEADER` | Optional. One more header, written `Name: value`, for an endpoint that wants a version header. |

There is no default endpoint and no default model. The flags `--url`, `--format`, `--model` and `--key-env` set the
same things for one command.

## Use

```
brevio-core scan --diff main
brevio-core-assist explain "<one finding line>"       # why the line breaks the rule
brevio-core-assist suggest-fix "<one finding line>"   # a corrected line, printed only
```

Pass a finding line exactly as `brevio-core scan` prints it. Run the command in the folder the path is relative to,
or name that folder with `--root`.

## What it sends, and when

Each command makes one request. The request holds the question, the rule's text and the one source line the finding
points at. It holds no path, no other line of the file and no other file.

Before anything leaves the machine, the command prints the whole request body and asks `Send it? [y/N]`. Only a yes
sends it. `--yes` skips the question but still prints the body. `--dry-run` prints the body and stops. Without a
terminal to ask and without `--yes`, it does not send.

The key is read from the variable you named. It goes only into the request's header (`Authorization: Bearer` for
`chat`, `x-api-key` for `messages`) and is never printed.

A suggested fix is printed for you to read. The plugin does not edit your files.

## Exit codes

The exit codes are 0 when the answer was printed or the dry run finished, 1 when the endpoint failed, 2 for a usage error, and 3 when the plugin is off or the request was not sent.

## Tests

The tests run against a fake endpoint on this machine. From this folder, with brevio-core installed or its tree one
level up:

```
PYTHONPATH=.:.. python -m unittest discover -s tests
```
