.. multi-step-workflow

Tapis Workflow Installation and Execution
=========================================

Install GeneFlow and Tapis dependencies into a Python virtual environment:

.. code-block:: bash

    # create a virtual python environment
    mkdir -p ~/geneflow
    cd ~/geneflow
    python -m venv gfpy
    source gfpy/bin/activate

    # install geneflow
    pip3 install geneflow

    # install tapis/agave library
    git clone -b python-3.7 https://gitlab.com/geneflow/dependencies/agavepy.git
    pip3 install ./agavepy

Create an Tapis/Agave token. There are a couple ways to do this, but in the CDC environment, the recommended method is the `cobra-cli` module:

.. code-block:: bash

    module load cobra-cli
    auth-tokens-create -u [username]
    
Create a personal execution system. This is required to be able to register apps to the system:

.. code-block:: bash

    cobra-systems-create

Create the GeneFlow config file with the following contents:

.. code-block:: bash

    vim ./config.yaml

.. code-block:: text

    class: config
    gfVersion: v2.0
    local:
      agave:
        connection_type: agave-cli
      database:
        path: database.db
        type: sqlite

Create the GeneFlow agave-params file with the following contents. Replace `[username]` with your username and replace `[date]` with the date associated with your personal execution system.

.. code-block:: bash

    vim ./agave-params.yaml

.. code-block:: text

    %YAML 1.1
    ---
    agave:
      # prefix for app name. For user apps, use your username.
      # For public apps, use 'public'.
      appsPrefix: [username]

      # must have publish rights to the execution system
      executionSystem: cobra-hpc-aspen-[username]-[date]

      # location of your agave home directory
      deploymentSystem: tapis-default-public-storage

      # Apps directory where app assets will be uploaded.
      # This must be an absolute path.
      appsDir: /[username]/apps-gf

      # location of workflow test data, absolute path.
      testDataDir: /[username]/testdata-gf

Install the workflow and register with Agave:

.. code-block:: bash

    gf install-workflow -g https://gitlab.com/workflows/bwa-gf2.git -c --make-apps --config ./config.yaml -e local --agave-params ./agave-params.yaml bwa-gf2 

Run the workflow, replace `[username]` with your username:

.. code-block:: bash

    gf --log-level debug run ./bwa-gf2 -o ./output -n test-agave -w agave://tapis-default-public-storage/[username]/.geneflow/work --in.files ./bwa-gf2/data/reads --in.reference ./bwa-gf2/data/reference/poliovirus_strain_Sabin1.fasta --ec default:agave --ep default.slots:2


