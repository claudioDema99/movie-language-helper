"""Print installed third-party package licenses from Python metadata."""

from importlib.metadata import Distribution, distributions

PROJECT_DISTRIBUTION = "movie-language-helper-backend"
LICENSE_CLASSIFIER_PREFIX = "License :: "


def distribution_name(distribution: Distribution) -> str:
    """Return the normalized display name from package metadata."""
    return distribution.metadata.get("Name", "UNKNOWN")


def distribution_license(distribution: Distribution) -> str:
    """Return the best standardized license declaration available."""
    expression = distribution.metadata.get("License-Expression")
    if expression:
        return expression

    declared_license = distribution.metadata.get("License")
    if declared_license:
        return declared_license

    classifiers = distribution.metadata.get_all("Classifier") or []
    license_classifiers = [
        classifier.removeprefix(LICENSE_CLASSIFIER_PREFIX)
        for classifier in classifiers
        if classifier.startswith(LICENSE_CLASSIFIER_PREFIX)
    ]
    if license_classifiers:
        return "; ".join(license_classifiers)

    return "UNKNOWN"


def main() -> None:
    """Print one stable, reviewable line per installed third-party package."""
    installed = sorted(
        distributions(), key=lambda item: distribution_name(item).lower()
    )
    for distribution in installed:
        name = distribution_name(distribution)
        if name == PROJECT_DISTRIBUTION:
            continue
        print(f"{name}=={distribution.version} | {distribution_license(distribution)}")


if __name__ == "__main__":
    main()
