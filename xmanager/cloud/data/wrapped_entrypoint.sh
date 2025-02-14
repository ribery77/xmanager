#!/bin/bash

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

python3 -c "import caip_utils; caip_utils.create_workerpool_address_env_vars_script('./map_xm_env_vars')"
source ./map_xm_env_vars
ARGS=($(python3 -c "import caip_utils; import sys; caip_utils.print_workerpool_address_args(sys.argv)" $@ | tr -d '[],'))
./entrypoint.sh ${ARGS[@]}
