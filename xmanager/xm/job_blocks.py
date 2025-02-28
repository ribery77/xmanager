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
"""Data classes for job-related abstractions."""

import abc
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, TypeVar, Union

import attr

from xmanager.xm import pattern_matching
from xmanager.xm import utils

UserArgs = Union[Mapping, Sequence, 'SequentialArgs']


class SequentialArgs:
  """A sequence of positional and keyword arguments for a binary.

  Unix command line arguments are just a list of strings. But it is very common
  to simulate keyword arguments in a --key=value form. It is not uncommon to
  only have keyword arguments. Therefore we allow providing args as:

  Dicts:
    {'foo': 'space bar', 'with_magic': True} -> --foo='space bar' --with_magic
    Argument order is preserved.
  Lists:
    ['--foo', 'space bar'] -> --foo 'space bar'
  SequentialArgs (which allows to represent a mix of the two above):
    xm.merge_args({'foo': 'bar'}, ['--'], {'n': 16}) -> --foo=bar -- --n=16

  SequentialArgs provides a convenient merging semantics: if a value is given
  for an existing keyword argument, it will be overriden rather than appended,
  which allows to specify default values and override them later:

    xm.merge_args({'foo': '1', 'bar': '42'}, {'foo': '2'}) -> --foo=2 --bar=42

  SequentialArgs is immutable, but you can get a copy with updated value:

    args = xm.merge_args({'foo': '1', 'bar': '42'})
    args = xm.merge_args(args, {'foo': '2'})

  We only allow appending new arguments (positional and keyword) and overriding
  keyword arguments. Removal and inserting to the middle is not supported.
  """

  @attr.s(auto_attribs=True)
  class _RegularItem:
    value: Any

  @attr.s(auto_attribs=True)
  class _KeywordItem:
    name: str

  def __init__(self) -> None:
    """Constucts an empty SequentialArgs.

    Prefer using xm.merge_args to construct SequentialArgs objects.
    """
    self._items: List[Union[SequentialArgs._RegularItem,
                            SequentialArgs._KeywordItem]] = []
    self._kwvalues: Dict[str, Any] = {}

  def _ingest_regular_item(self, value: Any) -> None:
    self._items.append(SequentialArgs._RegularItem(value))

  def _ingest_keyword_item(self, name: str, value: Any) -> None:
    if name not in self._kwvalues:
      self._items.append(SequentialArgs._KeywordItem(name))
    self._kwvalues[name] = value

  def _merge_from(self, args: 'SequentialArgs') -> None:
    """Merges another instance of SequentialArgs into self."""

    def import_regular_item(item: SequentialArgs._RegularItem):
      self._ingest_regular_item(item.value)

    def import_keyword_item(item: SequentialArgs._KeywordItem):
      self._ingest_keyword_item(item.name, args._kwvalues[item.name])  # pylint: disable=protected-access

    matcher = pattern_matching.match(
        import_regular_item,
        import_keyword_item,
    )
    for item in args._items:  # pylint: disable=protected-access
      matcher(item)

  @staticmethod
  def from_collection(collection: Optional[UserArgs]) -> 'SequentialArgs':
    """Populates a new instance from a given collection."""
    result = SequentialArgs()
    if collection is None:
      return result

    def check_for_string(args: str) -> None:
      raise ValueError(
          f'Tried to construct xm.SequentialArgs from a string: {args!r}. '
          f'Wrap it in a list: [{args!r}] to make it a single argument.')

    def import_sequential_args(args: SequentialArgs) -> None:
      result._merge_from(args)  # pylint: disable=protected-access

    def import_mapping(collection: Mapping[Any, Any]) -> None:
      for key, value in collection.items():
        result._ingest_keyword_item(str(key), value)  # pylint: disable=protected-access

    def import_sequence(collection: Sequence[Any]) -> None:
      for value in collection:
        result._ingest_regular_item(value)  # pylint: disable=protected-access

    matcher = pattern_matching.match(check_for_string, import_sequential_args,
                                     import_mapping, import_sequence)
    matcher(collection)
    return result

  def to_list(
      self,
      escaper: Callable[[Any], str],
      kwargs_joiner: Callable[[str, str], str] = utils.trivial_kwargs_joiner
  ) -> List[str]:
    """Exports items as a list ready to be passed into the command line."""

    def export_regular_item(item: SequentialArgs._RegularItem) -> str:
      return escaper(item.value)

    def export_keyword_item(item: SequentialArgs._KeywordItem) -> str:
      value = self._kwvalues[item.name]
      if isinstance(value, bool):
        return escaper(f"--{'' if value else 'no'}{item.name}")
      else:
        return kwargs_joiner(escaper(f'--{item.name}'), escaper(value))

    matcher = pattern_matching.match(
        export_regular_item,
        export_keyword_item,
    )
    return [matcher(item) for item in self._items]

  def to_dict(self, kwargs_only: bool = False) -> Dict[str, Any]:
    """Exports items as a dictionary.

    Args:
      kwargs_only: Whether to skip positional arguments.

    Returns:
      The sought dictionary.
    """
    if kwargs_only:
      return self._kwvalues

    def export_regular_item(
        item: SequentialArgs._RegularItem) -> Tuple[str, Any]:
      return (str(item.value), True)

    def export_keyword_item(
        item: SequentialArgs._KeywordItem) -> Tuple[str, Any]:
      return (item.name, self._kwvalues[item.name])

    matcher = pattern_matching.match(
        export_regular_item,
        export_keyword_item,
    )
    return dict([matcher(item) for item in self._items])

  def __eq__(self, other) -> bool:
    return isinstance(other, SequentialArgs) and all([
        self._items == other._items,
        self._kwvalues == other._kwvalues,
    ])

  def __repr__(self) -> str:
    return f"[{', '.join(self.to_list(repr))}]"


def merge_args(*operands: Union[SequentialArgs, UserArgs]) -> SequentialArgs:
  """Merges several arguments collections into one left-to-right."""
  result = SequentialArgs()
  for operand in operands:
    if not isinstance(operand, SequentialArgs):
      operand = SequentialArgs.from_collection(operand)
    result._merge_from(operand)  # pylint: disable=protected-access
  return result


class ExecutableSpec(abc.ABC):
  """Executable specification describes what code / computation to run.

  Use one of the functions declared in xm/packagables.py to create a spec:
   * xm.binary - a prebuilt executable program.
   * xm.bazel_binary - an executable built with Bazel.
   * xm.container - a prebuilt Docker container.
   * xm.bazel_container - a Docker container built with Bazel.
   * xm.python_container - a Docker container running python code.
   * xm.dockerfile_container - a Docker container built with dockerfile.

  An executable spec must be turned into an Executable using
  Experiment.package() in order to be used in a Job.

  WARNING: `ExecutableSpec`s are supposed to be implementation-agnostic. That
  means there should be no backend-specific class inheriting `ExecutableSpec`.
  """

  @property
  @abc.abstractmethod
  def name(self) -> str:
    raise NotImplementedError


@attr.s(auto_attribs=True)
class Executable(abc.ABC):
  """Executable describes the final location of a packaged executable spec.

  An executable depends on the executable specification and the executor
  specification. Experiment's implementation knows how to handle each type of
  executable.

  Attributes:
    name: An automatically populated name for the executable. Used for assigning
      default names to `Job`s.
  """

  name: str


class ExecutorSpec(abc.ABC):
  """Executor spec describes the location of the runtime environment.

  For a list of supported ExecutorSpecs see a list of executors below.
  """


class Executor(abc.ABC):
  """Executor describes the runtime environment of a Job.

  Concrete supported executors are listed in xm_local/executors.py:
    * xm_local.Local
    * xm_local.Caip
    * xm_local.Kubernetes
  """

  @classmethod
  @abc.abstractmethod
  def Spec(cls) -> ExecutorSpec:  # pylint: disable=invalid-name
    raise NotImplementedError


@attr.s(auto_attribs=True)
class Packageable:
  """Packageable describes what to build and its static parameters."""

  executable_spec: ExecutableSpec
  executor_spec: ExecutorSpec
  args: SequentialArgs = attr.ib(
      factory=list, converter=SequentialArgs.from_collection)  # pytype: disable=annotation-type-mismatch
  env_vars: Dict[str, str] = attr.ib(converter=dict, default=attr.Factory(dict))


class Constraint(abc.ABC):
  """Constraint describes the requirements for where a job group can run.

  Some examples of constraints include:

    * same virtual machine;
    * same virtual private Cloud subnetwork;
    * same network fabric;
    * same geographic location.
  """


JobGeneratorType = Callable[..., Awaitable]
JobType = Union['Job', 'JobGroup', JobGeneratorType]


@attr.s(auto_attribs=True)
class Job:
  """Job describes a unit of computation to be run.

  Attributes:
    executable: What to run -- one of `xm.Experiment.package` results.
    executor: Where to run -- one of `xm.Executor` subclasses.
    name: Name of the job. Must be unique within the context (work unit). By
      default it is constructed from the executable. Used for naming related
      entities such as newly created containers.
    args: Command line arguments to pass. This can be dict, list or
      xm.SequentialArgs. Dicts are most convenient for keyword flags.
      {'batch_size': 16} is passed as --batch_size=16. If positional arguments
      are needed one can use a list or xm.SequentialArgs.
    env_vars: Environment variables to apply.
  """

  executable: Executable
  executor: Executor
  name: Optional[str] = None
  args: SequentialArgs = attr.ib(
      factory=list, converter=SequentialArgs.from_collection)  # pytype: disable=annotation-type-mismatch
  env_vars: Dict[str, str] = attr.Factory(dict)


class JobGroup:
  """JobGroup describes a set of jobs that run under shared constraints.

  Use named arguments to give jobs meaningful names:

  ```
  JobGroup(
      learner=Job(learner_executable, executor),
      actor=Job(actor_executable, executor),
  )
  ```

  JobGroups provide the gang scheduling concept: Jobs inside them would be
  scheduled / descheduled simultaneously. Note that schedulers may not always be
  able to enforce that.

  JobGroups may include more fine grained constraints:

  ```
  JobGroup(
      learner=Job(tpu_learner_executable, executor),
      preprocessor=Job(preprocessor_executable, executor),
      constraints=[xm_impl.SameMachine()],
  )
  ```

  To express sophisticated requirements JobGroups can be nested:

  ```
  JobGroup(
      eval=Job(eval_executable, executor),
      colocated_learner_and_actor=JobGroup(
          learner=Job(tpu_learner_executable, executor),
          actor=Job(actor_executable, executor),
          constraints=[xm_impl.SameMachine()],
      ),
  )
  ```

  Attributes:
    jobs: A mapping of names to jobs.
    constraints: A list of additional scheduling constraints.
  """

  jobs: Dict[str, JobType]
  constraints: List[Constraint]

  def __init__(self,
               *,
               constraints: Optional[Sequence[Constraint]] = None,
               **jobs: JobType) -> None:
    """Builds a JobGroup.

    Args:
      constraints: List of additional scheduling constraints. Keyword only arg.
      **jobs: Jobs / job groups that constitute the group passed as kwargs.
    """
    self.jobs = jobs
    self.constraints = list(constraints) if constraints else []


JobTypeVar = TypeVar('JobTypeVar', Job, JobGroup, JobGeneratorType)
