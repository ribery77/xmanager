# Copyright 2021 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Packaging for execution on Cloud."""
from typing import Any, Optional

from xmanager import xm
from xmanager.cloud import auth
from xmanager.cloud import build_image
from xmanager.cloud import docker_lib
from xmanager.docker import docker_adapter
from xmanager.xm import pattern_matching
from xmanager.xm_local import executables as local_executables
from xmanager.xm_local import executors as local_executors


def _get_push_image_tag(executor_spec: xm.ExecutorSpec) -> Optional[str]:
  """Get the push_image_tag from executor or None."""

  def _get_push_image_tag_caip(spec: local_executors.CaipSpec):
    return spec.push_image_tag

  def _get_push_image_tag_kubernetes(spec: local_executors.KubernetesSpec):
    return spec.push_image_tag

  def _throw_on_unknown_executor(executor: Any):
    raise TypeError(f'Unsupported executor specification: {executor!r}. ')

  return pattern_matching.match(
      _get_push_image_tag_caip,
      _get_push_image_tag_kubernetes,
      _throw_on_unknown_executor,
  )(
      executor_spec)


def _package_container(packageable: xm.Packageable,
                       container: xm.Container) -> xm.Executable:
  """Matcher method for packaging `xm.Container`.

  If the user builds an image with the same repository name as an image in a
  remote Cloud registry, the user should push the image before running XManager,
  because XManager will not push a local image in the packaging step.

  Unless the container's image path already matches the GCR project prefix, we
  always pull the container and push it to push_image_tag location. This avoids
  a potential permissions error where the user has permissions to read an image,
  but the Cloud service agent does not have permissions. If container.image_path
  already points to the GCR project, we skip pushing because the image should
  already be in the destination location.

  Args:
    packageable: Packageable containing Executor and Executable.
    container: Container specifying image path.

  Returns:
    GoogleContainerRegistryImage Executable.
  """
  gcr_project_prefix = 'gcr.io/' + auth.get_project_name()
  if container.image_path.startswith(
      gcr_project_prefix) or not docker_lib.is_docker_installed():
    return local_executables.GoogleContainerRegistryImage(
        name=packageable.executable_spec.name,
        image_path=container.image_path,
        args=packageable.args,
        env_vars=packageable.env_vars,
    )

  instance = docker_adapter.instance()
  client = instance.get_client()
  print(f'Pulling {container.image_path}...')
  repository, tag = instance.split_tag(container.image_path)
  image_id = instance.pull_image(container.image_path)
  image = client.images.get(image_id)

  push_image_tag = _get_push_image_tag(packageable.executor_spec)
  if not push_image_tag:
    if repository.startswith(gcr_project_prefix):
      # If the image path already points to the project's GCR, reuse it.
      push_image_tag = f'{repository}:{tag}'
    else:
      # Otherwise, create a new image repository inside the project's GCR.
      push_image_tag = f'{gcr_project_prefix}/{repository}:{tag}'
  image.tag(push_image_tag)
  print(f'Pushing {push_image_tag}...')
  client.images.push(push_image_tag)
  return local_executables.GoogleContainerRegistryImage(
      name=packageable.executable_spec.name,
      image_path=push_image_tag,
      args=packageable.args,
      env_vars=packageable.env_vars,
  )


def _package_dockerfile(packageable: xm.Packageable, dockerfile: xm.Dockerfile):
  """Matcher method for packaging `xm.Dockerfile`."""
  push_image_tag = _get_push_image_tag(packageable.executor_spec)
  if not push_image_tag:
    gcr_project_prefix = 'gcr.io/' + auth.get_project_name()
    tag = docker_lib.create_tag()
    push_image_tag = f'{gcr_project_prefix}/{dockerfile.name}:{tag}'

  image = build_image.build_by_dockerfile(dockerfile.path,
                                          dockerfile.dockerfile, push_image_tag)
  if docker_lib.is_docker_installed():
    build_image.push(image)
  return local_executables.GoogleContainerRegistryImage(
      name=packageable.executable_spec.name,
      image_path=push_image_tag,
      args=packageable.args,
      env_vars=packageable.env_vars,
  )


def _package_python_container(
    packageable: xm.Packageable,
    python_container: xm.PythonContainer) -> xm.Executable:
  """Matcher method for packaging `xm.PythonContainer`."""
  push_image_tag = _get_push_image_tag(packageable.executor_spec)
  image = build_image.build(python_container, packageable.args,
                            packageable.env_vars, push_image_tag)
  if docker_lib.is_docker_installed():
    build_image.push(image)
  return local_executables.GoogleContainerRegistryImage(
      name=packageable.executable_spec.name,
      image_path=image,
  )


def _throw_on_unknown_executable(packageable: xm.Packageable,
                                 executable: xm.ExecutableSpec):
  raise TypeError('Unsupported executable specification '
                  f'for Cloud packaging: {executable!r}')


_CLOUD_PACKAGING_ROUTER = pattern_matching.match(
    _package_container,
    _package_dockerfile,
    _package_python_container,
    _throw_on_unknown_executable,
)


def package_cloud_executable(
    packageable: xm.Packageable,
    executable_spec: xm.ExecutableSpec) -> xm.Executable:
  return _CLOUD_PACKAGING_ROUTER(packageable, executable_spec)
