"""ScanCode 32 JSON subset; unknown fields are bounded then discarded."""
from ...core.scanner import ScanStatus
from ..models import DependencyEvidence, LicenseProviderResult, PackageEvidence
from .base import (
    InvalidProviderOutput, array, atom, deduplicate_facts, license_fact, note_partial,
    object_value, package_from_purl, provenance, relative_path, requirement, sanitize_result,
    validate_tree, version, record_error, ProviderLimitExceeded, append_license,
)


class ScanCodeResultParser:
    def parse(self, data: dict, limits, expected_version: str | None = None) -> LicenseProviderResult:
        validate_tree(data, limits)
        data = object_value(data)
        headers = array(data.get("headers"), 32)
        if not headers:
            raise InvalidProviderOutput()
        header = object_value(headers[-1])
        if header.get("tool_name") != "scancode-toolkit":
            raise InvalidProviderOutput()
        release = version(header.get("tool_version"))
        if not release or release.split(".")[0] != "32" or (expected_version and expected_version != release):
            raise InvalidProviderOutput()
        result = LicenseProviderResult("scancode", release, "local-cli", ScanStatus.SUCCESS, "ok")
        files = array(data.get("files"), limits.max_files)
        packages = array(data.get("packages", []), limits.max_packages)
        dependencies = array(data.get("dependencies", []), limits.max_dependencies)
        by_uid = {}
        counts = {"packages": 0, "dependencies": 0, "detections": 0}

        def count(kind, maximum):
            counts[kind] += 1
            if counts[kind] > maximum:
                raise ProviderLimitExceeded()

        def dependency(item, path, owner=None):
            count("dependencies", limits.max_dependencies)
            item = object_value(item)
            prov = provenance("scancode", release, "dependency_metadata", "local-cli")
            package = package_from_purl(item.get("purl"), prov)
            dep = DependencyEvidence(relative_path(path), package,
                                     "direct" if item.get("is_direct", True) is True else "transitive",
                                     atom(item.get("scope"), optional=True), requirement(item.get("extracted_requirement")),
                                     owner, [prov])
            result.dependencies.append(dep)
            fact = license_fact(path, None, prov, package)
            fact.dependencies.append(dep)
            append_license(result, fact, limits)
            return dep

        def package_data(item, paths):
            count("packages", limits.max_packages)
            item = object_value(item)
            prov = provenance("scancode", release, "declared_package_metadata", "local-cli")
            if item.get("purl"):
                package = package_from_purl(item["purl"], prov)
                if item.get("name") and atom(item["name"]) != package.name:
                    raise InvalidProviderOutput()
                if item.get("version") and atom(item["version"]) != package.version:
                    raise InvalidProviderOutput()
            elif item.get("name"):
                package = PackageEvidence(atom(item.get("name")), atom(item.get("version"), optional=True), None, [prov])
            else:
                # ScanCode 32.5 emits anonymous manifest containers for files
                # such as requirements.txt and Cargo.lock. They are not broken
                # packages and must not be assigned a fabricated identity.
                package = None
            if package is not None:
                result.packages.append(package)
                if isinstance(item.get("package_uid"), str):
                    by_uid[item["package_uid"]] = package
            for path in array(paths, limits.max_files):
                path = relative_path(path)
                declared = item.get("declared_license_expression_spdx") or item.get("declared_license_expression")
                # Anonymous containers may carry a useful correlated license,
                # but missing metadata is not itself a package-scoped fact.
                if package is not None or declared is not None:
                    fact = license_fact(path, declared, prov, package,
                                        source_scope="package" if package else "project")
                    if package is not None:
                        owner = package.purl or package.identifier
                        for dep in array(item.get("dependencies", []), limits.max_dependencies):
                            try:
                                fact.dependencies.append(dependency(dep, path, owner))
                            except InvalidProviderOutput as error:
                                record_error(result, error)
                    append_license(result, fact, limits)
            if not paths:
                note_partial(result, "missing_source_location")

        for package in packages:
            try:
                package_data(package, object_value(package).get("datafile_paths", []))
            except InvalidProviderOutput as error:
                record_error(result, error)
        for dep in dependencies:
            try:
                item = object_value(dep)
                owner_package = by_uid.get(item.get("for_package_uid"))
                owner = (owner_package.purl or owner_package.identifier) if owner_package else None
                dependency(item, item.get("datafile_path"), owner)
            except InvalidProviderOutput as error:
                record_error(result, error)
        for file in files:
            try:
                file = object_value(file)
                if file.get("type") == "directory":
                    continue
                path = relative_path(file.get("path"))
                if file.get("scan_errors"):
                    errors = array(file["scan_errors"], limits.max_detections)
                    result.scan_error_count += len(errors)
                    note_partial(result, "upstream_scan_errors")
                for package in array(file.get("package_data", []), limits.max_packages):
                    try:
                        package_data(package, [path])
                    except InvalidProviderOutput as error:
                        record_error(result, error)
                owners = array(file.get("for_packages", []), limits.max_packages)
                package = by_uid.get(owners[0]) if len(owners) == 1 and isinstance(owners[0], str) else None
                for detection in array(file.get("license_detections", []), limits.max_detections):
                    try:
                        detection = object_value(detection)
                        detected = detection.get("license_expression_spdx") or detection.get("license_expression")
                        prov = provenance("scancode", release, "detected_license", "local-cli")
                        matches = array(detection.get("matches", []), limits.max_detections)
                        for match in matches or [None]:
                            count("detections", limits.max_detections)
                            match = object_value(match) if match is not None else {}
                            append_license(result, license_fact(
                                path, detected, prov, package, start=match.get("start_line"), end=match.get("end_line"),
                                score=match.get("score"), source_scope="package" if package else "project",
                            ), limits)
                    except InvalidProviderOutput as error:
                        record_error(result, error)
            except InvalidProviderOutput as error:
                record_error(result, error)
        if header.get("errors"):
            errors = array(header["errors"], limits.max_files)
            result.scan_error_count += len(errors)
            note_partial(result, "upstream_scan_errors")
        if any(counts[k] > m for k, m in (("packages", limits.max_packages),
                ("dependencies", limits.max_dependencies), ("detections", limits.max_detections))):
            raise InvalidProviderOutput()
        result.licenses = deduplicate_facts([result])
        result.packages = list({(p.name, p.version, p.purl): p for p in result.packages}.values())
        result.dependencies = list({
            (d.manifest_path, d.package.purl, d.package.identifier, d.package.name, d.package.version,
             d.relationship, d.scope, d.requirement, d.from_package): d
            for d in result.dependencies
        }.values())
        return sanitize_result(result)
