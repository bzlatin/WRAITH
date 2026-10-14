# Green-baseline workflow study

Sixteen fixed contracts exercise real smolagents orchestration before and after a
local feature implementation. A separate acceptance check tests the requested new
behavior; existing upstream tests remain unchanged.

[Results, CI integration, and reproduction](../../docs/workflow-value.md).
[Source pin](source.json) · [Feature request](task.json).

`base.patch` contains the three previously reviewed local fixes. `feature.patch`
adds current-step memory access for final-answer critics. Both derive from Hugging
Face's Apache-2.0 source; they are proposed local changes, not upstream releases.
See [the upstream license](UPSTREAM_LICENSE.txt). Other files are Wraith evaluation
tooling under the repository's Apache-2.0 license. No model requests are made.
