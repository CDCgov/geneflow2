.. apps

Creating GeneFlow Apps
======================

GeneFlow apps can be created and configured by editing the app's app.yaml file. An example config file can be found in the GeneFlow app template. 

Clone the template to your new app directory with the following command (Note: This repository is currently only available in the CDC GitLab repository):

.. code-block:: bash

    git clone https://gitlab.com/geneflow/apps/app-template-gf2.git new-app

Replace the folder name, 'new-app', with the name of your app. The app template contains the following file and directory structure:

.. code-block:: none

    ├── assets
    │       └── bwa-mem-gf2.sh
    ├── test
    │   ├── data
    │   └── test.sh
    ├── agave-app-def.json.j2
    ├── app.yaml
    └── README.rst

The 'assets' folder contains the app wrapper script, which is auto-generated based on the app.yaml file. The wrapper script is the app's execution entrypoint and contains logic to execute app binaries, scripts, or containers. Any binaries, scripts, or containers that need to be packaged with the app should be placed in the 'assets' folder. However, we recommend to containerize the app and publish it to a public repository or shared location.

The 'test' folder contains a 'data' folder with data used to test the app, and a shell script named 'test.sh'. The 'test.sh' script is auto-generated based on the app.yaml file. 

The 'agave-app-def.json.j2' is also auto-generated based on the app.yaml file, and represents the Agave app definitions. 

The 'README.rst' file should contain all documentation for the app and is automatically rendered in the source code repository. 

Finally, 'app.yaml' is the primary app definition file, which is described in detail below. Note that in this example app template, the wrapper script, 'bwa-mem-gf2.sh' will be auto-generated with a different name based on your app configuration. Thus, the 'bwa-mem-gf2.sh' file should be deleted prior to committing your app to a source control repository. Similarly, the 'test/data' folder contains sample data specific to the bwa-mem app, and may also be deleted or replaced with custom data for your app. 

GeneFlow App Config File
------------------------

The GeneFlow app definition file, named 'app.yaml' in the app repository, contains the following sections:

1. Metadata
2. Inputs and Parameters
3. App Execution Methods

In addition, the YAML file requires specific syntax to define execution blocks and conditional blocks. 

Metadata
~~~~~~~~

The app metadata section contains name, description, and source information.

name:
  Name of the GeneFlow app. We recommend to include a 'gf2' suffix in the app name. For example, if the app is meant to wrap the 'mem' function in BWA, the app name should be 'bwa-mem-gf2'. 

description:
  A title or short description of the app.

git:
  The full URL of the app's source repository. 

version:
  A string value that represents the app's version.


.. _apps-inputs-parameters:

Inputs and Parameters
~~~~~~~~~~~~~~~~~~~~~

Each app input and parameter item is defined in a subsection with the same name as the input/parameter. The 'output' parameter is required, and must be manually included in the app definition file. See the following section for details about the 'output' parameter. Each input or parameter subsection must have the following fields:

label:
  A title or short description of the field.

description:
  A long description of the field.

type:
  Data type of the field. For input fields, values can be: File, Directory, or Any. For parameter fields, values can be: File, Directory, Any, string, int, float, double, or long.

required:
  Specifies if the input/parameter is required. 

default:
  Specifies the default value of the field in the Agave or app definition, which would then be passed to the wrapper script. 

    Note: The following rules apply when handling 'required' and 'default' fields:

    1. If required == true, the default value is ignored.
    2. If required == false, and default is specified, the input/parameter is set to the default value in the Agave and app definitions.
    3. If required == false, and default is NOT specified, the input/parameter is only set if corresponding args are passed to the app.

script_default:
  Only for inputs. Specifies the default value of the field in the wrapper script and is over-written by the resolved "default" value. 

    Note: The following rules apply when handling 'required' and 'script_default' fields:

    1. If required == true, the script_default value is ignored.
    2. If required == false, and script_default is specified, the input is set to the default value in the wrapper script before arg parsing and allowed to be over-written by any args passed to the wrapper script.
    3. If required == false, and script_default is NOT specified, the input is only set if corresponding args are passed to the wrapper script.

test_value:
  (Optional) If specified, the input/parameter is set to this value in the test script.

post_exec:
  (Optional) List of shell/bash commands for post-processing of the input/parameter value after argument parsing. These commands modify or check the value of inputs/parameters; or create additional shell/bash variables for use in later parts of the script. By default, for 'File', 'Directory', or 'Any' types, the following commands are included in the wrapper script before any items listed in post_exec. If the name of the input/parameter is 'varname', then the following lines are added to the wrapper script:

    .. code-block:: bash

        VARNAME_FULL=$(readlink -f ${VARNAME})
        VARNAME_DIR=$(dirname ${VARNAME_FULL})
        VARNAME_BASE=$(basename ${VARNAME_FULL})

  See the section 'Execution Blocks' for information about the required format for execution blocks.

App Output
~~~~~~~~~~

The app 'output' parameter is associated with two additional variables for storing logs and temporary files:

    .. code-block:: bash

        LOG_FULL="${OUTPUT_DIR}/_log"
        TMP_FULL="${OUTPUT_DIR}/_tmp"

The LOG_FULL variable points to a directory that, once created, persists in the workflow intermediate and final output directory. LOG_FULL is optional, and must be manually created with a 'mkdir' command within the app config file prior to use. The '_log' directory must be accounted for when executing 'map' steps that process input folders. To exclude, a look-ahead regex can be used to filter the folder.  

The TMP_FULL variable must also be manually created, but also must be manually deleted within the "clean-up" section of the app configuration. The TMP_FULL directory may or may not persist in the workflow intermediate and output directory, depending on the execution context. 

.. _app-execution-methods:

App Execution Methods
~~~~~~~~~~~~~~~~~~~~~

Apps can be defined with multiple execution methods, with a single method being specified upon app execution. Execution methods define the medium of execution (i.e., singularity, docker, binary, script), as well as the location of the execution assets (i.e., included as part of the app package, in a shared location, from a repository, or pre-loaded/available in the environment PATH). 

This section of the config file includes the following fields and sub-sections:

pre_exec:
  This section contains a list of execution commands for environment preparation to be executed before any method-specific execution commands. Each pre_exec item is an execution block, as defined in the "Execution Blocks" section. 

exec_methods:
  This section contains a list of execution methods, with each list item containing the following:

    1. name: The name of the execution method, which can be one of the following or a custom method: singularity, docker, cdc-shared-singularity, environment, module.
    2. if: A conditional block, used to auto-detect the execution method. Each execution method conditional block is checked in the order of the listed execution method, and the first execution method with a satisfied condition is selected. See the "Conditional Blocks" section for more information.
    3. exec: A list of execution blocks to be executed if the method's condition is satisified. See the "Execution Blocks" section for more information.

post_exec:
  This section contains a list of execution commands for environment cleanup to be executed after any method-specific execution commands. Each post_exec item is an execution block, as defined in the "Execution Blocks" section.

Execution Blocks
~~~~~~~~~~~~~~~~

Execution blocks occur in input/parameter post processing sections (i.e., post_exec), as well as app pre (i.e., pre_exec), post (i.e., post_exec), and method-specific (i.e., exec_methods.exec) execution sections. Regardless of the location, all execution blocks are similarly formatted. Each of these sections is an array, with each array item defined with the following fields:

if:
  (Optional) Condition that must be satisfied for the item to be executed. See the section "Conditional Blocks" for more information.

else: 
  (Optional) If the "if" condition is present, and "else" is present, items in the "else" block are executed only if the "if" condition is not satisfied.

pipe:
  (Optional) If included, all remaining fields at this level are ignored. The pipe field is an array, with each array item containing an execution item. The order of execution items within "pipe" are piped in order of appearance. STDOUT is piped from one execution command to the next. Thus, within pipe execution items, the "stdout" field is ignored. Nested "pipe" fields are also ignored, preventing recursive piping. 

multi:
  (Optional) If included, all remaining fields at this level are ignored. The multi field is an array, with each array item containing an execution item. Each included execution item can be a pipe, or another multi, allowing for nested execution.

type:
  (Optional) Valid values are 'shell', 'singularity', and 'docker'. If omiitted, the default value is 'shell'. This specifies the type of execution.

run:
  Command to run. If type is singularity or docker, this is the command passed to the container executor after the container image is specified.

options:
  Container entrypoint command. If type is singularity or docker, this command is the singularity or docker sub-command and options. For singularity, the default is '-s exec'. For docker, the default is 'run --rm'.

image:
  If type is singularity or docker, this is the path, url, or name of the container.

args:
  Optional arguments to be passed to the command. This is expected to be an array, with each array item defined as follows:

    1. flag: (Optional) If present, the argument is pre-pended with this string.
    2. mount: (Optional) If present, and type is singularity or docker, the value should be the bash variable name representing one of the inputs or file/directory parameters. For example, an input of "filename" should be represented as "${FILENAME}". The file or directory's containing directory is mounted to the container using the option: "${FILENAME_DIR}:/dataX". If "value" is not specified, a value of "/dataX/${FILENAME_BASE}" is passed as an argument to the image. If "value" is present, the value is passed as an argument as follows: "/dataX/[value]"
    3. value: (Optional) If present, used as the argument value. If "mount" is also present, see above rules for "mount".

    Note that all "args" values are optional, and if none are specified, the argument is ignored.

stdout:
  (Optional) If present, the command's standard output will be piped here.

stderr:
  (Optional) If present, the command's standard error will be piped here.

All bash/shell commands in the "exec_methods" section has access to a number of pre-defined variables, including:

    1. ${SCRIPT_DIR}: directory of the wrapper script, which may not be the current directory. This depends on the execution environment.
    2. ${VARNAME}: One for each input/parameter, set to value of the input/parameter.
    3. ${VARNAME_FULL}: if input/parameter is a File, Directory, or Any, this is the full path of the input/parameter. 
    4. ${VARNAME_DIR}: if input/parameter is a File, Directory, or Any, this is the parent directory of the input/parameter.
    5. ${VARNAME_BASE}: if input/parameter is a File, Directory, or Any, this is the basename of the input/parameter.
    6. ${LOG_FULL}: location to store log files.
    7. ${TMP_FULL}: location to store temporary files.
    
Any additional bash/shell variables defined in the "post" section of each input/parameter, or defined in the "pre_exec" section are also available.

Conditional Blocks
~~~~~~~~~~~~~~~~~~

Conditional blocks are nestable conditional tests that can be included in execution blocks. Test conditions can be grouped with the following section keywords:

all:
  All items in this section must be satisified (i.e., [a AND b .. ]).

any:
  At least one item in this section must be satisfied (i.e., [a OR b .. ]).

none:
  None of the items in this section must be satisified (i.e., NOT [a AND b ..]).

These can be nested to any depth. Within these groups, test conditions can include the following, and parameters are passed as values (if single operand), or arrays (if two operands). Shell equivalent tests are shown below:

defined:
  -n value

not_defined:
  -z value

str_equal:
  value[0] = value[1]

not_str_equal:
  value[0] != value[1]

equal:
  value[0] -eq value[1]

not_equal:
  value[0] -ne value[1]

less:
  value[0] -lt value[1]

greater:
  value[0] -gt value[1]

less_equal:
  value[0] -le value[1]

greater_equal:
  value[0] -ge value[1]

file_exist:
  -f value

not_file_exist:
  ! -f value

dir_exist:
  -d value

not_dir_exist:
  ! -d value

exist:
  -e value

not_exist:
  ! -e value

in_path:
  command -v value >/dev/null 2>&1

str_contain:
  contains value[0] value[1]

not_str_contain:
  ! contains value[0] value[1]
  
Note that 'contains' is a function that tests for sub-strings. 'contains' evaluates to true (or 1) if value[1] is a sub-string of value[0]. All test conditions and section keywords must be list items. For example:

.. code-block:: none

    if:
    - all:
      - defined: '${VALUE}'
      - str_equal: ['${VALUE}', 'val']

Generating a GeneFlow App
-------------------------

Once the app 'config.yaml' file has been defined, the app can be generated. The app generation process creates the wrapper script, Agave definition, GeneFlow definition, and test script. To generate the app, run the following command from within the app directory:

.. code-block:: bash

    geneflow make-app .
