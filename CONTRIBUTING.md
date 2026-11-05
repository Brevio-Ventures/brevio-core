# Contributing

Thank you for helping. Small, focused changes are easiest to review.

## Sign your commits (DCO)

This project uses the Developer Certificate of Origin, not a CLA. Add a `Signed-off-by` line to every commit with
`git commit -s`. It says you wrote the change, or have the right to submit it under Apache-2.0.

```
Developer Certificate of Origin
Version 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I have the right to submit it under the open source
    license indicated in the file; or

(b) The contribution is based upon previous work that, to the best of my knowledge, is covered under an appropriate
    open source license and I have the right under that license to submit that work with modifications, whether
    created in whole or in part by me, under the same license (unless I am permitted to submit under a different
    license), as indicated in the file; or

(c) The contribution was provided directly to me by some other person who certified (a), (b) or (c) and I have not
    modified it.

(d) I understand and agree that this project and the contribution are public and that a record of the contribution
    (including all personal information I submit with it, including my sign-off) is maintained indefinitely and may
    be redistributed consistent with this project or the license(s) involved.
```

## Making a change

1. Fork the repository and make a branch.
2. Run the tests: `python -m unittest discover -s tests/pipeline/core_export -t .`
3. A new or changed rule needs a test, and its page under `docs/rules` must match the rule.
4. Open a pull request and fill in the template.

Never put secrets, personal data or private names in a commit. The leak test fails on stray URLs, email addresses and
paths.
