"""
Unit tests — JavaParser (discovery/codebase/java.py)

Covers:
  - Public method extraction
  - Private/package-private methods ignored
  - Static methods
  - Type mapping (int→INTEGER, String→STRING, boolean→BOOLEAN, double→NUMBER)
  - Generic parameters (List<String>, Map<K,V>)
  - Javadoc → description
  - Class name used as slug prefix
  - @Override + other annotations
  - Interface default methods
  - Varargs (String... args)
  - Protected methods included
  - toString/hashCode/equals skipped
"""
from pathlib import Path

import pytest

from mcp_forge.discovery.codebase.java import JavaParser
from mcp_forge.models import ParameterType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(source: str, tmp_path: Path) -> list:
    f = tmp_path / "MyClass.java"
    f.write_text(source, encoding="utf-8")
    return JavaParser().extract(f, tmp_path)


# ---------------------------------------------------------------------------
# Basic extraction
# ---------------------------------------------------------------------------

def test_public_method_extracted(tmp_path):
    source = """\
public class UserService {
    public String getUser(int userId) {
        return "";
    }
}
"""
    tools = parse(source, tmp_path)
    assert len(tools) == 1
    # Java slug: camelCase lowercased without underscore splitting (getUser → getuser)
    assert "getuser" in tools[0].name


def test_private_method_ignored(tmp_path):
    source = """\
public class MyService {
    private void internalHelper() {}
    public void doWork() {}
}
"""
    tools = parse(source, tmp_path)
    assert len(tools) == 1
    assert "dowork" in tools[0].name


def test_package_private_method_ignored(tmp_path):
    source = """\
public class MyClass {
    void packageMethod() {}
    public void publicMethod() {}
}
"""
    tools = parse(source, tmp_path)
    # Only public/protected methods extracted; slug is camelCase lowercased
    assert all("publicmethod" in t.name for t in tools)


def test_protected_method_extracted(tmp_path):
    source = """\
public class Base {
    protected String buildQuery(int limit) { return ""; }
}
"""
    tools = parse(source, tmp_path)
    assert len(tools) == 1


def test_static_method_extracted(tmp_path):
    source = """\
public class Utils {
    public static int parse(String s) { return 0; }
}
"""
    tools = parse(source, tmp_path)
    assert len(tools) == 1


def test_interface_method_without_body_not_extracted(tmp_path):
    """2026-10-12, found while testing on a real Java project made mostly of interfaces (~2,000
    files): an interface method ("public void foo(String s);", no body) has no implementation to
    call, unlike a method of a concrete class. Almost all the tools extracted from that project
    pointed to methods without a body: never executable."""
    source = """\
public interface Listener {
    void onEvent(String name);
}
"""
    tools = parse(source, tmp_path)
    assert tools == []


def test_abstract_method_without_body_not_extracted(tmp_path):
    source = """\
public abstract class Base {
    public abstract int compute(int x);
}
"""
    tools = parse(source, tmp_path)
    assert tools == []


def test_concrete_method_with_body_still_extracted_alongside_abstract(tmp_path):
    """Sanity check: the filter must remove ONLY methods without a body: a concrete method in the
    same class is still extracted (static: an instance method of an abstract class is left out
    for another reason, see the instantiability tests)."""
    source = """\
public abstract class Base {
    public abstract int compute(int x);
    public static int helper(int x) { return x + 1; }
}
"""
    tools = parse(source, tmp_path)
    assert len(tools) == 1
    assert tools[0].metadata["function"] == "helper"


# ---------------------------------------------------------------------------
# Instantiability (`new Class().m(...)`, as the generated Java driver calls it)
# ---------------------------------------------------------------------------
# 2026-10-13, reported by the evaluator on a real Java project as a
# "major and systematic" defect: instance methods of abstract classes,
# of interfaces (`default`) or of classes without a public no-argument
# constructor were exposed, then called with `new Class()`: a guaranteed
# compilation failure. Only the really callable ones remain.

@pytest.mark.parametrize("source", [
    "public abstract class Base {\n    public int helper(int x) { return x; }\n}\n",
    "public interface Api {\n    default int helper(int x) { return x; }\n    public static int util(int x) { return x; }\n}\n",
    "public enum Mode { A;\n    public int helper(int x) { return x; }\n}\n",
    "public class Svc {\n    private Svc() {}\n    public int helper(int x) { return x; }\n}\n",
    "public class Svc {\n    public Svc(String name) {}\n    public int helper(int x) { return x; }\n}\n",
    "class Hidden {\n    public int helper(int x) { return x; }\n}\n",
])
def test_instance_method_of_non_instantiable_type_skipped(tmp_path, source):
    tools = parse(source, tmp_path)
    assert all(t.metadata["is_static"] for t in tools)
    assert not any(t.metadata["function"] == "helper" for t in tools)


def test_static_method_of_non_instantiable_type_kept(tmp_path):
    source = "public abstract class Base {\n    public static int util(int x) { return x; }\n}\n"
    tools = parse(source, tmp_path)
    assert [t.metadata["function"] for t in tools] == ["util"]


@pytest.mark.parametrize("source", [
    "public class Svc {\n    public int helper(int x) { return x; }\n}\n",
    "public final class Svc {\n    public Svc() {}\n    public Svc(String n) {}\n    public int helper(int x) { return x; }\n}\n",
    "public class Svc {\n    private static final Object O = new Svc() { };\n    public int helper(int x) { return x; }\n}\n",
])
def test_instance_method_of_instantiable_class_kept(tmp_path, source):
    tools = parse(source, tmp_path)
    assert [t.metadata["function"] for t in tools] == ["helper"]


# ---------------------------------------------------------------------------
# Skipped names
# ---------------------------------------------------------------------------

def test_tostring_skipped(tmp_path):
    source = """\
public class Model {
    public String toString() { return ""; }
    public int hashCode() { return 0; }
    public boolean equals(Object o) { return false; }
}
"""
    tools = parse(source, tmp_path)
    assert tools == []


# ---------------------------------------------------------------------------
# Class name as prefix
# ---------------------------------------------------------------------------

def test_class_name_prefix(tmp_path):
    source = """\
public class OrderService {
    public void createOrder(String id) {}
}
"""
    tools = parse(source, tmp_path)
    assert tools[0].name.startswith("orderservice_")


# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("java_type,expected", [
    ("int", ParameterType.INTEGER),
    ("long", ParameterType.INTEGER),
    ("double", ParameterType.NUMBER),
    ("float", ParameterType.NUMBER),
    ("boolean", ParameterType.BOOLEAN),
    ("String", ParameterType.STRING),
])
def test_type_mapping(tmp_path, java_type, expected):
    source = f"""\
public class Svc {{
    public void method({java_type} value) {{}}
}}
"""
    tools = parse(source, tmp_path)
    assert tools[0].parameters[0].type == expected


# ---------------------------------------------------------------------------
# Generics
# ---------------------------------------------------------------------------

def test_list_param_extracted(tmp_path):
    """Regression 2026-10-01: `List<T>` must be typed ARRAY, not STRING: otherwise a caller that
    passes a real Python list to a `List<Double>` parameter (e.g. `sumList(List<Double> numbers)`)
    has it passed as a scalar on the MCP side, which makes the tool unusable."""
    source = """\
import java.util.List;
public class Svc {
    public void process(List<String> items) {}
}
"""
    tools = parse(source, tmp_path)
    assert len(tools[0].parameters) == 1
    assert tools[0].parameters[0].type == ParameterType.ARRAY


def test_primitive_array_param_typed_as_array_not_element_type(tmp_path):
    """Regression 2026-10-01, found in a real evaluation report: a `double[] numbers` parameter was
    typed NUMBER (a single float) instead of ARRAY, because the base type was computed AFTER the
    `[]` were removed from the type, losing any trace that it was an array."""
    source = """\
public class Utils {
    public static double sumList(double[] numbers) { return 0; }
}
"""
    tools = parse(source, tmp_path)
    assert tools[0].parameters[0].type == ParameterType.ARRAY


def test_c_style_array_declaration_also_typed_as_array(tmp_path):
    """C style: brackets attached to the name rather than to the type (`double numbers[]`), still
    valid in Java."""
    source = """\
public class Utils {
    public static double sumList(double numbers[]) { return 0; }
}
"""
    tools = parse(source, tmp_path)
    assert tools[0].parameters[0].type == ParameterType.ARRAY


def test_type_annotation_inside_array_type_normalized(tmp_path):
    """2026-10-13, a real Java project: `byte @NotNull [] message` gave the Java type "byte []"
    (with a space), hence a badly typed driver."""
    source = """\
public class Utils {
    public static void send(byte @NotNull [] message) {}
}
"""
    tools = parse(source, tmp_path)
    assert tools[0].metadata["java_param_types"] == ["byte[]"]
    assert tools[0].parameters[0].type == ParameterType.ARRAY


def test_multi_arg_generic_param_extracted(tmp_path):
    """Generic with a comma (`Pair<String, Integer>`): a single parameter. (Formerly tested with
    `Map<...>`, now left out on purpose: no string can produce a Map, see _JDK_UNBUILDABLE.)"""
    source = """\
public class Svc {
    public void configure(Pair<String, Integer> settings) {}
}
"""
    tools = parse(source, tmp_path)
    assert len(tools[0].parameters) == 1


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------

def test_override_annotation_method_extracted(tmp_path):
    source = """\
public class Impl implements Base {
    @Override
    public String process(String input) { return input; }
}
"""
    tools = parse(source, tmp_path)
    assert len(tools) == 1


def test_param_annotation_stripped(tmp_path):
    source = """\
public class Svc {
    public void save(@NotNull String name) {}
}
"""
    tools = parse(source, tmp_path)
    assert len(tools[0].parameters) == 1
    assert tools[0].parameters[0].name == "name"


# ---------------------------------------------------------------------------
# Javadoc
# ---------------------------------------------------------------------------

def test_javadoc_as_description(tmp_path):
    source = """\
public class Svc {
    /**
     * Creates a new user account.
     */
    public void createUser(String email) {}
}
"""
    tools = parse(source, tmp_path)
    assert "user" in tools[0].description.lower() or "account" in tools[0].description.lower()


def test_javadoc_inline_tags_kept_not_truncated(tmp_path):
    """2026-10-13, a real Java project: "* Creates a lookup entry for {": all the text after the
    first `@` (including an INLINE `{@link X}`) was dropped, and the asterisk of the first line
    kept."""
    source = """\
public class Keys {
    /**
     * Creates a lookup entry for {@link Color} in the
     * {@link Catalog#COLORS catalog}. Uses {@code key}.
     *
     * @param key the value's key in the catalog
     * @return a new lookup entry
     */
    public static int create(Key key) { return 0; }
}
"""
    tool = parse(source, tmp_path)[0]
    assert tool.description == "Creates a lookup entry for Color in the catalog. Uses key."
    assert tool.parameters[0].description == "the value's key in the catalog (Java: Key)"
    assert tool.response_description.startswith("a new lookup entry")


def test_javadoc_not_borrowed_from_previous_method(tmp_path):
    source = """\
public class Svc {
    /** Documented one. */
    public static int a(int x) { return x; }
    public static int b(int x) { return x; }
}
"""
    tools = {t.metadata["function"]: t for t in parse(source, tmp_path)}
    assert tools["a"].description == "Documented one."
    assert "Documented" not in tools["b"].description


def test_no_javadoc_fallback_description_mentions_signature(tmp_path):
    source = """\
public class Svc {
    public static int runJob(int id, String name) { return 0; }
}
"""
    tool = parse(source, tmp_path)[0]
    assert tool.description == "Calls the Java method Svc.runJob(int, String)."
    assert tool.parameters[0].description == "Java int"


def test_no_javadoc_fallback_description(tmp_path):
    source = """\
public class Svc {
    public void runJob(int id) {}
}
"""
    tools = parse(source, tmp_path)
    assert tools[0].description  # non-empty


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata_language(tmp_path):
    source = "public class A { public void go() {} }\n"
    tools = parse(source, tmp_path)
    assert tools[0].metadata["language"] == "java"


def test_metadata_class_and_function(tmp_path):
    source = """\
public class Billing {
    public void charge(String id) {}
}
"""
    tools = parse(source, tmp_path)
    assert tools[0].metadata["class"] == "Billing"
    assert tools[0].metadata["function"] == "charge"


def test_metadata_is_static_true_for_static_method(tmp_path):
    """2026-10-05, needed to generate a real execution driver: a static method is called as
    `ClassName.method(...)`, an instance method needs `new ClassName().method(...)`."""
    source = """\
public class Utils {
    public static boolean isPrime(int n) { return true; }
}
"""
    tools = parse(source, tmp_path)
    assert tools[0].metadata["is_static"] is True


def test_metadata_is_static_false_for_instance_method(tmp_path):
    source = """\
public class Billing {
    public void charge(String id) {}
}
"""
    tools = parse(source, tmp_path)
    assert tools[0].metadata["is_static"] is False


# ---------------------------------------------------------------------------
# Source root detection (-sourcepath of the generated Java driver)
# ---------------------------------------------------------------------------

def test_source_root_detected_from_package_and_relative_path(tmp_path):
    """2026-10-12, found while testing on a real multi-module Java project:
    "src/generated/java/org/example/..." has "src/generated/java" as its root, deduced by comparing
    the real relative path of the file with its `package` declaration."""
    pkg_dir = tmp_path / "src" / "generated" / "java" / "org" / "example" / "keys"
    pkg_dir.mkdir(parents=True)
    f = pkg_dir / "ColorKeys.java"
    f.write_text(
        "package org.example.keys;\n"
        "public class ColorKeys {\n"
        "    public static int create(String key) { return 0; }\n"
        "}\n",
        encoding="utf-8",
    )
    tools = JavaParser().extract(f, tmp_path)
    assert len(tools) == 1
    assert tools[0].metadata["java_source_root"] == "src/generated/java"


def test_source_root_empty_when_no_package_declaration(tmp_path):
    tools = parse("public class Utils {\n    public static int f() { return 0; }\n}\n", tmp_path)
    assert tools[0].metadata["java_source_root"] == ""


def test_java_package_metadata_populated(tmp_path):
    """2026-10-13, needed so that the generated driver (in the default package) can explicitly
    import the target class from a REAL package: a reference by short name does not compile
    without it."""
    pkg_dir = tmp_path / "src" / "main" / "java" / "org" / "example" / "keys"
    pkg_dir.mkdir(parents=True)
    f = pkg_dir / "ColorKeys.java"
    f.write_text(
        "package org.example.keys;\n"
        "public class ColorKeys {\n"
        "    public static int create(String key) { return 0; }\n"
        "}\n",
        encoding="utf-8",
    )
    tools = JavaParser().extract(f, tmp_path)
    assert tools[0].metadata["java_package"] == "org.example.keys"


def test_java_package_empty_when_no_package_declaration(tmp_path):
    tools = parse("public class Utils {\n    public static int f() { return 0; }\n}\n", tmp_path)
    assert tools[0].metadata["java_package"] == ""


def _write(root: Path, name: str, body: str) -> Path:
    f = root / f"{name}.java"
    f.write_text(body, encoding="utf-8")
    return f


def test_param_of_project_interface_without_string_factory_skipped(tmp_path):
    """2026-10-13, a real Java project: some parameter types are interfaces implemented by the
    running application; no string can produce one. The tools that take one failed on every call.
    Another callable overload of the same name stays exposed."""
    _write(tmp_path, "Handler", "public interface Handler { String getName(); }\n")
    f = _write(tmp_path, "Metrics", (
        "public class Metrics {\n"
        "    public static int of(Handler handler, String name) { return 0; }\n"
        "    public static int of(String name) { return 1; }\n"
        "}\n"
    ))
    tools = JavaParser().extract(f, tmp_path)
    assert [t.metadata["java_param_types"] for t in tools] == [["String"]]


def test_array_of_unbuildable_project_type_skipped(tmp_path):
    """2026-10-13, reported by the evaluator (a varargs parameter of a project class): each
    element of an array is converted like the base type; if that type cannot be built, neither can
    the array."""
    _write(tmp_path, "Field", "public class Field {\n    public Field(String k, Object v) {}\n}\n")
    f = _write(tmp_path, "Records", "public class Records {\n    public static int create(Field... data) { return 0; }\n}\n")
    assert JavaParser().extract(f, tmp_path) == []


@pytest.mark.parametrize("decl", [
    "public enum Mode { A, B }\n",
    "public interface Mode { static Mode of(String raw) { return null; } }\n",
    "public final class Mode { public Mode(final String raw) {} }\n",
    "public abstract class Mode { public static Mode parse(@NotNull String raw) { return null; } }\n",
])
def test_param_of_project_type_buildable_from_string_kept(tmp_path, decl):
    _write(tmp_path, "Mode", decl)
    f = _write(tmp_path, "Svc", "public class Svc {\n    public static int run(Mode mode) { return 0; }\n}\n")
    assert len(JavaParser().extract(f, tmp_path)) == 1


def test_param_of_jdk_interface_without_string_factory_skipped(tmp_path):
    """`Map`, `Function`... (JDK, outside the project): no string can produce them, as the
    evaluator reported on a method that takes a Map."""
    f = _write(tmp_path, "Svc", (
        "public class Svc {\n"
        "    public static int a(Map<String, Object> parent) { return 0; }\n"
        "    public static int b(java.util.function.Function<String, String> fn) { return 0; }\n"
        "    public static int c(String s) { return 0; }\n"
        "}\n"
    ))
    assert [t.metadata["function"] for t in JavaParser().extract(f, tmp_path)] == ["c"]


def test_project_class_shadowing_jdk_name_judged_by_project_index(tmp_path):
    """A project type with the same name as a JDK type (e.g. org.example.model.Comparator) is
    judged by the project index, not by the JDK list."""
    _write(tmp_path, "Comparator", "public enum Comparator { ON, OFF }\n")
    f = _write(tmp_path, "Svc", "public class Svc {\n    public static int a(Comparator c) { return 0; }\n}\n")
    assert len(JavaParser().extract(f, tmp_path)) == 1


def test_param_of_external_type_kept(tmp_path):
    """A type outside the project (JDK, library): not judged, left to McpForgeConvert at run
    time."""
    f = _write(tmp_path, "Svc", "public class Svc {\n    public static int run(Key key) { return 0; }\n}\n")
    assert len(JavaParser().extract(f, tmp_path)) == 1


def test_maven_gradle_test_sources_skipped(tmp_path):
    """2026-10-13, a real Java project: the JUnit classes of src/test/java were exposed as
    tools."""
    pkg = tmp_path / "test" / "proj" / "src" / "test" / "java" / "a"
    pkg.mkdir(parents=True)
    f = pkg / "ClockTest.java"
    f.write_text("package a;\npublic class ClockTest {\n    public static int f() { return 0; }\n}\n", encoding="utf-8")
    assert JavaParser().extract(f, tmp_path / "test" / "proj") == []


def test_project_living_under_a_test_folder_still_parsed(tmp_path):
    """The filter applies to the RELATIVE path: a project located in a folder named "test" (a
    real case: ...\\test\\<project>\\api) is not ignored because of it."""
    root = tmp_path / "test" / "proj"
    pkg = root / "src" / "main" / "java" / "a"
    pkg.mkdir(parents=True)
    f = pkg / "Util.java"
    f.write_text("package a;\npublic class Util {\n    public static int f() { return 0; }\n}\n", encoding="utf-8")
    assert len(JavaParser().extract(f, root)) == 1


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_empty_file_returns_empty(tmp_path):
    f = tmp_path / "Empty.java"
    f.write_text("", encoding="utf-8")
    assert JavaParser().extract(f, tmp_path) == []


def test_missing_file_returns_empty(tmp_path):
    f = tmp_path / "Ghost.java"
    assert JavaParser().extract(f, tmp_path) == []
