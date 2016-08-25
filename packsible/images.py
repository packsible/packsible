import sys
from docker import Client


def find_best_docker_base_image(config, dependencies):
    best_match_size = 0

    dependencies_set = set(dependencies)

    # All images must have a base
    dependencies_set.add('base')

    docker_base_url = config.get('docker_base_url',
                                 'unix://var/run/docker.sock')

    docker_client = Client()

    images = filter(
        lambda img: (img.get('Labels', {}) or {}).get('packsible.provides') is not None,
        docker_client.images()
    )

    for image in images:
        image_provides = set(image['Labels']['packsible.provides'].split(','))

        if image_provides.issubset(dependencies_set):
            intersection = dependencies_set.intersection(image_provides)
            intersection_size = len(intersection)

            if intersection_size > best_match_size:
                repo_tag = image['RepoTags'][0]
                if repo_tag == '<none>:<none>':
                    continue
                best_match_size = intersection_size
                best_match = {
                    "name": image['RepoTags'][0],
                    "provides": list(image_provides),
                }

    if best_match_size < 1:
        raise Exception("Must have a base image installed")

    return best_match
