"""Read ORT analyzer/scanner JSON without running any ORT component."""
from __future__ import annotations

import json

from ...core.scanner import ScanStatus
from ..models import DependencyEvidence, LicenseProviderResult, PackageEvidence
from .base import (
    InvalidProviderOutput, array, atom, deduplicate_facts, expression, license_fact, note_partial,
    object_value, package_from_purl, provenance, relative_path, sanitize_result, validate_tree, version,
    record_error, ProviderLimitExceeded, append_license,
)


def identifier(value):
    if not isinstance(value, str) or len(value.split(":")) != 4:
        raise InvalidProviderOutput()
    kind, namespace, name, release = value.split(":")
    atom(kind)
    for part in namespace.split("/"):
        atom(part, optional=True)
    return kind, namespace, atom(name), atom(release, optional=True)


def provenance_key(value):
    value = object_value(value)
    if "vcs_info" in value:
        vcs = object_value(value["vcs_info"])
        identity = ["vcs", vcs.get("type"), vcs.get("url"),
                    value.get("resolved_revision") or vcs.get("revision"), vcs.get("path", "")]
    elif "source_artifact" in value:
        artifact = object_value(value["source_artifact"])
        identity = ["artifact", artifact.get("url"), artifact.get("hash")]
    else:
        raise InvalidProviderOutput()
    # Join keys remain transient; URLs and hashes never enter projected provenance.
    return json.dumps(identity, sort_keys=True)


class OrtResultParser:
    def parse(self, data: dict, limits) -> LicenseProviderResult:
        validate_tree(data, limits)
        data = object_value(data)
        analyzer_run = object_value(data.get("analyzer", {}))
        scanner_run = object_value(data.get("scanner", {}))
        if not analyzer_run and not scanner_run:
            raise InvalidProviderOutput()
        releases = {version(object_value(run.get("environment", {})).get("ort_version"))
                    for run in (analyzer_run, scanner_run) if run}
        if None in releases or len(releases) != 1:
            raise InvalidProviderOutput()
        release = releases.pop()
        result = LicenseProviderResult("ort", release, "result-import", ScanStatus.SUCCESS, "ok")
        analyzer = object_value(analyzer_run.get("result")) if analyzer_run else {}
        projects = array(analyzer.get("projects") if analyzer_run else [], limits.max_packages)
        raw_packages = array(analyzer.get("packages") if analyzer_run else [], limits.max_packages)
        scanner_provenances = array(scanner_run.get("provenances") if scanner_run else [], limits.max_packages)
        scanner_results = array(scanner_run.get("scan_results") if scanner_run else [], limits.max_detections)
        package_by_id, raw_by_id, project_paths = {}, {}, {}
        dependency_paths, scope_projects = {}, {}

        def package(item, is_project=False):
            item = object_value(item)
            # Older ORT JSON can wrap curated packages in a package member.
            if "package" in item:
                item = object_value(item["package"])
            identity = item.get("id")
            kind, namespace, name, package_version = identifier(identity)
            prov = provenance("ort", release, "declared_package_metadata", "result-import")
            if item.get("purl"):
                fact = package_from_purl(item["purl"], prov)
                if fact.name != name or fact.version != package_version:
                    raise InvalidProviderOutput()
            else:
                fact = PackageEvidence(name, package_version, None, [prov])
            fact.identifier = identity
            path = relative_path(item.get("definition_file_path")) if is_project else None
            if identity in package_by_id and package_by_id[identity] != fact:
                raise InvalidProviderOutput()
            if identity not in package_by_id and len(package_by_id) >= limits.max_packages:
                raise ProviderLimitExceeded()
            package_by_id[identity], raw_by_id[identity] = fact, item
            result.packages.append(fact)
            if is_project:
                project_paths[identity] = path
                scope_projects.setdefault(f"{namespace}:{name}:{package_version or ''}", []).append((identity, path))

        for item, is_project in [*((item, True) for item in projects), *((item, False) for item in raw_packages)]:
            try:
                package(item, is_project)
            except InvalidProviderOutput as error:
                record_error(result, error)
        if len(result.packages) > limits.max_packages:
            raise InvalidProviderOutput()

        def add_dependency(dep_id, path, scope, parent_id, direct):
            identifier(dep_id)
            if dep_id not in package_by_id:
                kind, namespace, name, dep_version = identifier(dep_id)
                if len(package_by_id) >= limits.max_packages:
                    raise ProviderLimitExceeded()
                prov = provenance("ort", release, "dependency_metadata", "result-import")
                package_by_id[dep_id] = PackageEvidence(name, dep_version, provenance=[prov], identifier=dep_id)
                result.packages.append(package_by_id[dep_id])
                note_partial(result, "missing_package_metadata")
            prov = provenance("ort", release, "dependency_metadata", "result-import")
            dep = DependencyEvidence(path, package_by_id[dep_id], "direct" if direct else "transitive",
                                     atom(scope), None, parent_id,
                                     [prov])
            if len(result.dependencies) >= limits.max_dependencies:
                raise ProviderLimitExceeded()
            result.dependencies.append(dep)
            dependency_paths.setdefault(dep_id, set()).add(path)
            fact = license_fact(path, None, prov, dep.package)
            fact.dependencies.append(dep)
            append_license(result, fact, limits)

        # Classical project.scopes trees remain supported, but are traversed iteratively.
        for project in projects:
            try:
                project = object_value(project)
                project_id = project.get("id")
                path = project_paths[project_id]
                for scope in array(project.get("scopes", []), limits.max_dependencies):
                    scope = object_value(scope)
                    scope_name = atom(scope.get("name"))
                    stack = [(x, project_id, True) for x in array(scope.get("dependencies", []), limits.max_dependencies)]
                    while stack:
                        node, parent, direct = stack.pop()
                        node = object_value(node)
                        add_dependency(node.get("id"), path, scope_name, parent, direct)
                        if node.get("issues"):
                            note_partial(result, "upstream_analysis_issues")
                        stack.extend((x, node["id"], False) for x in array(node.get("dependencies", []), limits.max_dependencies))
            except (InvalidProviderOutput, KeyError) as error:
                record_error(result, error)

        # Current ORT shared graphs use pkg indices, fragments and node-index edges.
        graphs = object_value(analyzer.get("dependency_graphs", {}))
        for graph in graphs.values():
            try:
                graph = object_value(graph)
                ids = array(graph.get("packages", []), limits.max_packages)
                for value in ids:
                    identifier(value)
                nodes = array(graph.get("nodes", []), limits.max_dependencies)
                if graph.get("scope_roots") and not nodes:
                    note_partial(result, "unsupported_legacy_graph")
                    continue
                adjacency = {i: [] for i in range(len(nodes))}
                lookup = {}
                for i, node in enumerate(nodes):
                    node = object_value(node)
                    index, fragment = node.get("pkg", 0), node.get("fragment", 0)
                    if type(index) is not int or not 0 <= index < len(ids) or type(fragment) is not int or fragment < 0:
                        raise InvalidProviderOutput()
                    if (index, fragment) in lookup:
                        raise InvalidProviderOutput()
                    lookup[index, fragment] = i
                for edge in array(graph.get("edges", []), limits.max_dependencies):
                    edge = object_value(edge)
                    src, dst = edge.get("from"), edge.get("to")
                    if any(type(i) is not int or i not in adjacency for i in (src, dst)):
                        raise InvalidProviderOutput()
                    adjacency[src].append(dst)
                for qualified, roots in object_value(graph.get("scopes", {})).items():
                    prefix, separator, scope_name = qualified.rpartition(":")
                    candidates = scope_projects.get(prefix, []) if separator else []
                    if len(candidates) != 1:
                        note_partial(result, "unmapped_dependency_scope")
                        continue
                    pid, path = candidates[0]
                    scope_name = atom(scope_name)
                    visited = set()
                    stack = []
                    for root in array(roots, limits.max_dependencies):
                        root = object_value(root)
                        stack.append((lookup[root.get("root"), root.get("fragment", 0)], pid, True))
                    while stack:
                        index, parent, direct = stack.pop()
                        dep_id = ids[nodes[index].get("pkg", 0)]
                        edge_key = (parent, index, direct)
                        if edge_key not in visited:
                            visited.add(edge_key)
                            add_dependency(dep_id, path, scope_name, parent, direct)
                        node_key = ("node", index)
                        if node_key in visited:
                            continue
                        visited.add(node_key)
                        stack.extend((child, dep_id, False) for child in adjacency[index])
            except (InvalidProviderOutput, KeyError, TypeError) as error:
                record_error(result, error, "invalid_dependency_graph")

        # Metadata facts use project declaration paths where known; otherwise remain
        # package inventory, never a fabricated local source location.
        for identity, item in raw_by_id.items():
            paths = {project_paths[identity]} if identity in project_paths else dependency_paths.get(identity, set())
            try:
                declared = array(item.get("declared_licenses", []), limits.max_detections)
                processed = object_value(item.get("declared_licenses_processed", {}))
                values = [("declared_package_metadata", value) for value in declared]
                if processed.get("spdx_expression"):
                    values.append(("processed_declared_license", processed["spdx_expression"]))
                if item.get("concluded_license"):
                    values.append(("concluded_license", item["concluded_license"]))
                if not values:
                    values = [("declared_package_metadata", None)]
                for path in paths:
                    for kind, value in values:
                        prov = provenance("ort", release, kind, "result-import")
                        append_license(result, license_fact(path, value, prov, package_by_id[identity]), limits)
                if not paths:
                    note_partial(result, "missing_source_location")
            except InvalidProviderOutput as error:
                record_error(result, error)

        # Scanner results are associated by ORT provenance, NOT array order.
        by_provenance = {}
        for item in scanner_provenances:
            try:
                item = object_value(item)
                identity = item.get("id")
                identifier(identity)
                key = provenance_key(item.get("package_provenance"))
                by_provenance.setdefault(key, []).append(identity)
                if item.get("sub_repositories"):
                    note_partial(result, "nested_provenance_not_mapped")
            except InvalidProviderOutput as error:
                record_error(result, error, "unmapped_provenance")
        for scan in scanner_results:
            try:
                scan = object_value(scan)
                scanner = object_value(scan.get("scanner"))
                scanner_name = atom(scanner.get("name")).lower()
                origin = "scancode" if scanner_name == "scancode" else atom(scanner_name)
                scanner_version = version(scanner.get("version"))
                prov = provenance("ort", release, "detected_license", "result-import", origin, scanner_version)
                identities = by_provenance.get(provenance_key(scan.get("provenance")), [])
                if not identities:
                    note_partial(result, "unmapped_provenance")
                    continue
                summary = object_value(scan.get("summary"))
                if summary.get("issues"):
                    note_partial(result, "upstream_scan_errors")
                for finding in array(summary.get("licenses", []), limits.max_detections):
                    finding = object_value(finding)
                    loc = object_value(finding.get("location"))
                    for identity in identities:
                        package = package_by_id.get(identity)
                        if package is None:
                            note_partial(result, "missing_package_metadata")
                            continue
                        append_license(result, license_fact(
                            loc.get("path"), finding.get("license"), prov, package,
                            start=loc.get("start_line"), end=loc.get("end_line"), score=finding.get("score"),
                            source_scope="package",
                        ), limits)
            except InvalidProviderOutput as error:
                record_error(result, error)
        if len(result.licenses) > limits.max_detections or len(result.dependencies) > limits.max_dependencies:
            raise InvalidProviderOutput()
        if analyzer.get("issues") or scanner_run.get("issues"):
            note_partial(result, "upstream_analysis_issues")
        result.licenses = deduplicate_facts([result])
        result.packages = list({(p.name, p.version, p.purl): p for p in result.packages}.values())
        return sanitize_result(result)
