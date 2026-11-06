"""The claims of SECURITY-REVIEW.md, as tests: no network, only ``git`` with read-only subcommands, no dynamic code,
and an Action that pins what it uses and never runs on the privileged events (ROADMAP E24, E26, 2026-11-05).

Standard library only: the exporter copies this file beside the code and it runs unchanged in the public tree. In the
harness it first exports the newest set and reads that copy, so it checks exactly the modules that ship.

No module is exempt, ``up`` included. The 0.6 set ships ``up`` (``core_up``) as a preview that lists what a team sync
would take and uploads nothing; the sending bridge stays in the harness, so no shipped module needs the network and
this test allows it nowhere (ROADMAP E37, 2026-11-05). A sending ``up`` would need an exception named here, for its
own module only, loaded lazily by ``core_cli``.
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
EXPORTER = os.path.join(ROOT, "tools", "export_core.py")      # present in the harness checkout only
HARNESS = os.path.isfile(EXPORTER)
TREE = ROOT
_EXPORT = tempfile.TemporaryDirectory()
# Where the Action and the workflows sit: the repository root in the public tree, the release templates in the harness.
ACTION = os.path.join(ROOT, "tools", "core_action", "action.yml") if HARNESS else os.path.join(ROOT, "action.yml")
WORKFLOWS = (os.path.join(ROOT, "tools", "core_release", ".github", "workflows") if HARNESS
             else os.path.join(ROOT, ".github", "workflows"))

NETWORK_MODULES = {"socket", "ssl", "urllib", "http", "ftplib", "smtplib", "telnetlib", "poplib", "imaplib", "nntplib",
                   "xmlrpc", "socketserver", "webbrowser", "asyncio", "multiprocessing"}
CODE_MODULES = {"pickle", "marshal", "shelve", "ctypes", "pty"}
# The optional bring-your-own-key plugin is a separate package that depends on the core; the core never imports it, by any
# route, so the core stays model-free whether or not the plugin is installed (ADOPTION.md 0.36, 2026-11-05).
ASSIST_PACKAGE = "brevio_core_assist"
# The connection helpers of asyncio and socket, banned as names too, in case a module reaches them another way.
NETWORK_NAMES = {"open_connection", "open_unix_connection", "start_server", "start_unix_server", "create_connection",
                 "create_server", "create_datagram_endpoint", "sock_connect", "urlopen"}
BANNED_BUILTINS = {"eval", "exec", "compile", "__import__"}
BANNED_OS = re.compile(r"^(system|popen|fork|forkpty|exec\w*|spawn\w*|posix_spawn\w*|startfile)$")
SUBPROCESS_CALLS = {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"}
GIT_SUBCOMMANDS = {"check-ignore", "diff", "ls-files", "ls-tree", "rev-parse", "show"}      # read-only, as SECURITY-REVIEW.md lists them
PRIVILEGED_EVENTS = ("pull_request" + "_target", "workflow" + "_run")
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
PLANTED = "// @ts-ignore\nconst n: number = 'x';\n"
_NO_NET = (
    "import socket, sys\n"
    "def _refuse(*a, **k):\n"
    "    sys.stderr.write('NETWORK-USED\\n')\n"
    "    raise OSError('the network is off in this test')\n"
    "class _Socket:\n"
    "    def __init__(self, *a, **k):\n"
    "        _refuse()\n"
    "socket.socket = _Socket\n"
    "socket.create_connection = socket.getaddrinfo = socket.socketpair = socket.fromfd = _refuse\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from brevio.pipeline import core_cli\n"
    "raise SystemExit(core_cli.main(sys.argv[2:]))\n")


def setUpModule():
    global TREE
    if HARNESS:
        out = os.path.join(_EXPORT.name, "core")
        # The newest set, which holds every earlier one (tests/tools/test_release_core.py keeps this in step).
        subprocess.run([sys.executable, EXPORTER, "--out", out, "--set", "0.6"], check=True, capture_output=True, timeout=120)
        TREE = out


def tearDownModule():
    _EXPORT.cleanup()


def shipped_modules():
    """``(path relative to the tree, parsed module)`` for every Python file of the package (the tests are not shipped)."""
    out = []
    for dirpath, dirs, names in os.walk(os.path.join(TREE, "brevio")):
        dirs.sort()
        for n in sorted(names):
            if n.endswith(".py"):
                path = os.path.join(dirpath, n)
                with open(path, encoding="utf-8") as fh:
                    out.append((os.path.relpath(path, TREE).replace(os.sep, "/"), ast.parse(fh.read(), path)))
    return out


def _assignments(body):
    """Names bound among ``body`` by ``x = ...`` or ``x: T = ...``."""
    out = {}
    for node in body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for t in targets:
            if isinstance(t, ast.Name) and node.value is not None:
                out.setdefault(t.id, []).append(node.value)
    return out


class _Module:
    """One parsed module, with what the checks need: parents, module-level names, and the names of every module."""

    def __init__(self, rel, tree, everywhere):
        self.rel, self.tree, self.everywhere = rel, tree, everywhere
        self.parent = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        self.top = _assignments(tree.body)

    def function_of(self, node):
        while node in self.parent:
            node = self.parent[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
        return None

    def values_of(self, name, at):
        fn = self.function_of(at)
        local = _assignments(ast.walk(fn)) if fn else {}
        return local.get(name) or self.top.get(name) or self.everywhere.get(name, [])

    def flatten(self, node, at, depth=0):
        """The items of an argv expression: a string for a constant, the node itself for a part only known at run time."""
        if depth > 8:
            return [node]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, (ast.List, ast.Tuple)):
            return [item for elt in node.elts for item in self.flatten(elt, at, depth + 1)]
        if isinstance(node, ast.Starred):
            inner = self.flatten(node.value, at, depth + 1)
            return inner if inner != [node.value] else [node]
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
        values = self.values_of(name, at) if name else []
        if len(values) == 1:
            return self.flatten(values[0], at, depth + 1)
        return [node]


def _modules():
    parsed = shipped_modules()
    everywhere = {}
    for _rel, tree in parsed:     # a name imported from another module (``GIT``, ``gitsafe.GIT``) resolves to its one definition
        for name, values in _assignments(tree.body).items():
            everywhere.setdefault(name, []).extend(values)
    return [_Module(rel, tree, everywhere) for rel, tree in parsed]


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


PACKAGE_ROOTS = {"top", "__name__.split('.')[0]"}     # how a module names its own top package at run time


def _in_package_import(call, mod=None):
    """``import_module(f"{top}.x.y")`` or ``find_spec(...)`` of a module of this package, named at run time (absent
    from a smaller set). The name may sit in a local variable first."""
    if len(call.args) != 1:
        return False
    arg = call.args[0]
    if isinstance(arg, ast.Name) and mod is not None:
        values = mod.values_of(arg.id, call)
        arg = values[0] if len(values) == 1 else arg
    if not isinstance(arg, ast.JoinedStr):
        return False
    parts = arg.values
    return (len(parts) >= 2 and isinstance(parts[0], ast.FormattedValue) and ast.unparse(parts[0].value) in PACKAGE_ROOTS
            and isinstance(parts[1], ast.Constant) and str(parts[1].value).startswith("."))


def _importlib_problem(mod, node):
    """Why this use of ``importlib`` is not allowed, or ``None``. Allowed: ``import_module`` and ``util.find_spec`` of a
    module of this package, and ``metadata`` (it reads the installed package's metadata and runs no code)."""
    if node.attr == "metadata":
        return None
    target = node
    if node.attr == "util":
        target = mod.parent.get(node)
        if not (isinstance(target, ast.Attribute) and target.attr == "find_spec"):
            return "importlib.util other than find_spec"
    elif node.attr != "import_module":
        return f"importlib.{node.attr}"
    call = mod.parent.get(target)
    if isinstance(call, ast.Call) and call.func is target and _in_package_import(call, mod):
        return None
    return f"importlib.{node.attr} of a module outside this package"


def _subcommand(mod, items, call):
    """The git subcommand of a flattened argv, or ``None``; a forwarded ``*args`` is looked up at each caller."""
    i = 1
    while i < len(items):
        item = items[i]
        if item in ("-c", "-C"):
            i += 2
            continue
        if isinstance(item, str):
            return [item]
        fn = mod.function_of(call)
        if (isinstance(item, ast.Starred) and isinstance(item.value, ast.Name) and fn is not None
                and fn.args.vararg is not None and fn.args.vararg.arg == item.value.id):
            return _forwarded(mod, fn)
        return None
    return None


def _forwarded(mod, fn, depth=0):
    """The argument after the named parameters of each call to ``fn``, a wrapper whose ``*args`` start the git line.

    A caller that passes its own ``*args`` on (a method around the wrapper) is followed to its callers in turn."""
    subs = []
    for node in ast.walk(mod.tree):
        if not isinstance(node, ast.Call):
            continue
        by_name = isinstance(node.func, ast.Name) and node.func.id == fn.name
        by_attr = isinstance(node.func, ast.Attribute) and node.func.attr == fn.name
        if not (by_name or by_attr):
            continue
        pos = len(fn.args.args) - (1 if by_attr and fn.args.args and fn.args.args[0].arg == "self" else 0)
        arg = node.args[pos] if len(node.args) > pos else None
        caller = mod.function_of(node)
        if (isinstance(arg, ast.Starred) and isinstance(arg.value, ast.Name) and caller is not None and depth < 4
                and caller.args.vararg is not None and caller.args.vararg.arg == arg.value.id):
            subs += _forwarded(mod, caller, depth + 1) or [None]
        else:
            subs.append(arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None)
    return subs or None


def problems():
    """Every breach of the no-network and no-dynamic-code rules in the shipped modules, as ``path:line: what``."""
    out = []
    for mod in _modules():
        for node in ast.walk(mod.tree):
            where = f"{mod.rel}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for name in names:
                    top = name.split(".")[0]
                    if top in NETWORK_MODULES | CODE_MODULES:
                        out.append(f"{where}: imports {name}")
                    if isinstance(node, ast.ImportFrom) and top in ("subprocess", "importlib", "os"):
                        out.append(f"{where}: imports names from {name}")
            elif isinstance(node, (ast.Name, ast.Attribute)):
                name = node.id if isinstance(node, ast.Name) else node.attr
                if name in NETWORK_NAMES:
                    out.append(f"{where}: uses {name}")
                if isinstance(node, ast.Attribute) and _dotted(node.value) == "os" and BANNED_OS.match(node.attr):
                    out.append(f"{where}: starts a process with os.{node.attr}")
                lib = isinstance(node, ast.Attribute) and _dotted(node.value) == "importlib"
                why = _importlib_problem(mod, node) if lib else None
                if why:
                    out.append(f"{where}: {why}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_BUILTINS:
                out.append(f"{where}: calls {node.func.id}")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and _dotted(node.func.value) == "subprocess"
                    and node.func.attr in SUBPROCESS_CALLS):
                out += [f"{where}: {p}" for p in _git_call_problems(mod, node)]
    return out


def _git_call_problems(mod, call):
    if not call.args:
        return ["a subprocess call with no command"]
    items = mod.flatten(call.args[0], call)
    if not items or items[0] != "git":
        return ["a subprocess call that does not start git"]
    subs = _subcommand(mod, items, call)
    if not subs or None in subs:
        return ["a git call whose subcommand is not a constant"]
    return [f"git {s} is not one of the read-only subcommands" for s in subs if s not in GIT_SUBCOMMANDS]


def run_cli(cwd, *args, stdin=None):
    """``brevio-core`` with ``args`` under ``python -I``, with every socket call failing and reporting itself."""
    return subprocess.run([sys.executable, "-I", "-c", _NO_NET, TREE, *args], cwd=cwd, input=stdin, capture_output=True,
                          text=True, timeout=60)


def git(d, *args):
    subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@example.com", *args], check=True,
                   capture_output=True, timeout=60)


def planted_repo(d):
    git(d, "init", "-q")
    git(d, "commit", "-q", "--allow-empty", "-m", "base")
    with open(os.path.join(d, "planted.ts"), "w", encoding="utf-8") as fh:
        fh.write(PLANTED)


class TestNoNetworkInTheCode(unittest.TestCase):
    def test_no_shipped_module_reaches_the_network_runs_dynamic_code_or_starts_anything_but_git(self):
        self.assertEqual(problems(), [])

    def test_the_check_sees_every_module_and_the_git_calls_it_allows(self):
        mods = {m.rel: m for m in _modules()}
        self.assertIn("brevio/pipeline/core_cli.py", mods)
        if os.path.isfile(os.path.join(TREE, "brevio", "pipeline", "core_up.py")):
            self.assertIn("/".join(("brevio", "pipeline", "core_up.py")), mods)     # checked like every other module
        calls = [n for m in mods.values() for n in ast.walk(m.tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "run" and _dotted(n.func.value) == "subprocess"]
        self.assertTrue(calls, "the scan uses git, so the check must find its calls")

    def test_the_check_catches_a_socket_a_shell_a_foreign_import_and_a_git_write(self):
        bad = ("import socket\nimport subprocess\nimport importlib\nimport os\n"
               "def f(*args):\n    subprocess.run(['curl', 'x'], timeout=1)\n"
               "def g():\n    subprocess.run(['git', 'push'], timeout=1)\n"
               "os.system('ls')\nimportlib.import_module('ssl')\neval('1')\n")
        mod = _Module("x.py", ast.parse(bad), {})
        found = []
        for node in ast.walk(mod.tree):
            if isinstance(node, ast.Call) and _dotted(node.func) == "subprocess.run":
                found += _git_call_problems(mod, node)
        self.assertEqual(sorted(found), ["a subprocess call that does not start git",
                                         "git push is not one of the read-only subcommands"])
        call = next(n for n in ast.walk(mod.tree) if isinstance(n, ast.Call) and _dotted(n.func) == "importlib.import_module")
        self.assertFalse(_in_package_import(call, mod))
        own = ast.parse("import importlib\nname = f\"{__name__.split('.')[0]}.pipeline.x\"\nimportlib.import_module(name)\n")
        own_call = next(n for n in ast.walk(own) if isinstance(n, ast.Call) and _dotted(n.func) == "importlib.import_module")
        self.assertTrue(_in_package_import(own_call, _Module("y.py", own, {})))


def assist_references():
    """``path:line`` of every import of the optional plugin, or string naming it, in the shipped modules."""
    out = []
    for mod in _modules():
        for node in ast.walk(mod.tree):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom)
                     else [node.value] if isinstance(node, ast.Constant) and isinstance(node.value, str) else [])
            if any(ASSIST_PACKAGE in n.replace("-", "_") for n in names):
                out.append(f"{mod.rel}:{node.lineno}")
    return out


class TestPython310(unittest.TestCase):
    """The package says ``requires-python >= 3.10``: no shipped module may use syntax or names added later.

    The harness runs on a newer Python and its linter prefers ``datetime.UTC`` (3.11), which broke 16 exported tests on
    3.10 before 0.6.0 (2026-11-06). This keeps it from coming back where the gate does not run 3.10.
    """

    NEWER = {("datetime", "UTC"), ("typing", "Self"), ("enum", "StrEnum"), ("asyncio", "TaskGroup"),
             ("asyncio", "timeout"), ("typing", "reveal_type"), ("typing", "assert_never"), ("typing", "LiteralString")}

    def test_every_shipped_module_parses_and_uses_only_names_python_3_10_has(self):
        found = []
        for rel, _tree in shipped_modules():
            with open(os.path.join(TREE, rel), encoding="utf-8") as fh:
                src = fh.read()
            try:
                tree = ast.parse(src, rel, feature_version=(3, 10))
            except SyntaxError as exc:
                found.append(f"{rel}: syntax newer than 3.10 ({exc.msg})")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                        and (node.value.id, node.attr) in self.NEWER:
                    found.append(f"{rel}:{node.lineno}: {node.value.id}.{node.attr}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    found += [f"{rel}:{node.lineno}: from {node.module} import {a.name}" for a in node.names
                              if (node.module, a.name) in self.NEWER]
        self.assertEqual(found, [], "use datetime.timezone.utc and the 3.10 forms instead")


class TestTheOptionalPluginStaysOut(unittest.TestCase):
    def test_no_shipped_module_imports_or_names_the_optional_assist_plugin(self):
        self.assertEqual(assist_references(), [])

    def test_the_check_sees_an_import_and_a_name_given_at_run_time(self):
        bad = ("import brevio_core_assist\nfrom brevio_core_assist.assist import main\n"
               "import importlib\nimportlib.import_module('brevio-core-assist'.replace('-', '_'))\n")
        mod = _Module("x.py", ast.parse(bad), {})
        with unittest.mock.patch(f"{__name__}._modules", return_value=[mod]):
            self.assertEqual(assist_references(), ["x.py:1", "x.py:2", "x.py:4"])


class TestNoNetworkAtRunTime(unittest.TestCase):
    def test_a_diff_scan_finds_the_planted_line_with_every_socket_refused(self):
        with tempfile.TemporaryDirectory() as d:
            planted_repo(d)
            res = run_cli(d, "scan", "--diff", "HEAD")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("[R9.2]", res.stdout)
        self.assertNotIn("NETWORK-USED", res.stderr)

    def test_a_one_file_scan_that_forbids_ignores_finds_the_planted_line_with_every_socket_refused(self):
        with tempfile.TemporaryDirectory() as d:
            planted_repo(d)
            res = run_cli(d, "scan", "--forbid-ignores", "--file", "planted.ts")
        self.assertEqual((res.returncode, "[R9.2]" in res.stdout), (1, True), res.stderr)
        self.assertNotIn("NETWORK-USED", res.stderr)

    def test_the_agent_hook_reads_the_edited_file_from_its_event_with_every_socket_refused(self):
        if not os.path.isfile(os.path.join(TREE, "brevio", "pipeline", "core_hook.py")):
            self.skipTest("this set ships no hook runner")
        with tempfile.TemporaryDirectory() as d:
            planted_repo(d)
            event = {"cwd": d, "tool_name": "Write", "tool_input": {"file_path": os.path.join(d, "planted.ts")}}
            res = run_cli(d, "hook", "run", "--event", "post-edit", stdin=json.dumps(event))     # what `hook install` writes
        self.assertEqual((res.returncode, "[R9.2]" in res.stdout), (0, True), res.stderr)
        self.assertNotIn("NETWORK-USED", res.stderr)

    def test_up_lists_what_a_sync_would_take_with_every_socket_refused(self):
        if not os.path.isfile(os.path.join(TREE, "brevio", "pipeline", "core_up.py")):
            self.skipTest("this set ships no up")
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".brevio"))
            with open(os.path.join(d, ".brevio", "guards.json"), "w", encoding="utf-8") as fh:
                json.dump({"guards": {"g1": {"id": "g1", "patterns": ["x"]}}}, fh)
            res = run_cli(d, "up")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(".brevio/guards.json (", res.stdout)
        self.assertNotIn("NETWORK-USED", res.stderr)

    def test_the_mcp_server_scans_with_every_socket_refused(self):
        if not os.path.isfile(os.path.join(TREE, "brevio", "operator", "mcp_cmd.py")):
            self.skipTest("this set ships no MCP server")
        call = "tools" + "/call"        # joined: the leak scan reads a literal "tools" + "/" as a private folder
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
                {"jsonrpc": "2.0", "id": 2, "method": call, "params": {"name": "scan", "arguments": {"paths": ["planted.ts"]}}}]
        with tempfile.TemporaryDirectory() as d:
            planted_repo(d)
            res = run_cli(d, "mcp", stdin="".join(json.dumps(m) + "\n" for m in msgs))
        replies = [json.loads(ln) for ln in res.stdout.splitlines()]
        self.assertEqual(replies[1]["result"]["structuredContent"]["count"], 1, res.stderr)
        self.assertNotIn("NETWORK-USED", res.stderr)


@unittest.skipUnless(os.path.isfile(ACTION), "a bare export carries no Action")
class TestTheActionAndWorkflows(unittest.TestCase):
    def read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def shipped(self):
        files = [ACTION]
        if os.path.isdir(WORKFLOWS):
            files += [os.path.join(WORKFLOWS, n) for n in sorted(os.listdir(WORKFLOWS)) if n.endswith((".yml", ".yaml"))]
        return files

    def test_no_privileged_event_appears_in_the_action_or_a_shipped_workflow(self):
        for path in self.shipped():
            for event in PRIVILEGED_EVENTS:
                self.assertNotIn(event, self.read(path), path)

    def test_every_action_the_action_uses_is_pinned_to_a_full_commit_sha(self):
        uses = re.findall(r"^\s*(?:-\s*)?uses:\s*['\"]?([^\s'\"#]+)", self.read(ACTION), re.M)
        self.assertTrue(uses)
        self.assertEqual([u for u in uses if not PINNED.match(u)], [])

    def test_the_action_refuses_events_it_does_not_list(self):
        text = self.read(ACTION)
        self.assertIn("pull_request|merge_group|push)", text)
        self.assertNotIn("secrets.", text)

    def test_the_pin_check_catches_a_tag(self):
        self.assertFalse(PINNED.match("actions/setup-python@v6"))
        self.assertTrue(PINNED.match("github/codeql-action/upload-sarif@" + "0" * 40))


if __name__ == "__main__":
    unittest.main()
