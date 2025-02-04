.. _cha_development:

***********
Development
***********

In this section Everest development decisions are documented.


Architecture
============

The everest application is split into two components, a server component and a
client component.

.. figure:: images/architecture_design.png
    :align: center
    :width: 700px
    :alt: Everest architecture

    Everest architecture

Every time an optimization instance is ran by a user, the client component of the
application spawns an instance of the server component, which is started either on a
cluster node using LSF (when the `queue_system` is defined to be *lsf*) or on the
client's machine (when the `queue_system` is defined to be *local*).

Communication between the two components is done via an HTTP API.


Server HTTP API
===============
The Everest server component supports the following HTTP requests API. The Everest
server component was designed as an internal component that will be available as
long as the optimization process is running.


.. list-table:: Server HTTP API
   :widths: 25 25 75
   :header-rows: 1

   * - Method
     - Endpoint
     - Description
   * - GET
     - '/'
     - Check server is online
   * - GET
     - '/sim_progress'
     - Simulation progress information
   * - GET
     - '/opt_progress'
     - Optimization progress information
   * - POST
     - '/stop'
     - Signal everest optimization run termination. It will be called by the client when the optimization needs to be terminated in the middle of the run


EVEREST vs. ERT data models
===========================
EVEREST uses ERT for running an `experiment`. An `experiment` contains several `batches` (i.e., `ensembles`).
EVEREST `controls` are mapped to ERT `parameters` and serve as input to each forward model evaluation.
ERT generates `responses` for each forward model evaluation in the `batch`.
ERT writes these `responses` to storage in the `simulation_results` folder (per `batch` and per `realization`, as defined in the `runpath`).
These `responses` are mapped to `objectives` and `constraints` in EVEREST and read by `ropt` (i.e., the optimizer).
To summarize, every forward model evaluation for a single set of inputs/parameters (`controls`) and generated outputs/responses (`objectives` / `constraints`)
constitutes an ERT `realization` which is denoted in EVEREST as a `simulation`.

For `controls` in EVEREST, there is a distinction between `unperturbed controls` (i.e., current `objective function` value) and
`perturbed controls` (i.e., required to calculate the `gradient`).
Furthermore, when performing robust optimization (i.e., having multiple static `geo_realizations` / `model_realizations`, NOTE: not the same as an ERT `realization`) a `batch` contains
multiple `geo_realizations` (denoted by `<GEO_ID>`) and each `geo_realization` can contain several `simulations`
(i.e., forward model run). This is the key differences between the hierarchical data model of EVEREST and ERT (Fig 3).
NOTE: `<GEO_ID>` is inserted (and substituted) in the `run_path` for each `geo_realization`.

.. figure:: images/Everest_vs_Ert_01.png
    :align: center
    :width: 700px
    :alt: EVEREST vs. ERT data models

    Difference between `ensemble` in ERT and `batch` in EVEREST.

.. figure:: images/Everest_vs_Ert_02.png
    :align: center
    :width: 700px
    :alt: Additional explanation of Fig 3

    Different meaning of `realization` and `simulation`.

The mapping from data models in EVEREST and ERT is done in the `ropt` library, it maps from `realization` (ERT) to `<GEO_ID>` and `pertubation` (EVEREST) and vice versa.
`Batches` in EVEREST can contain several different configurations depending on the algorithm used. Gradient-based algorithms can have a single function
evaluation (`unperturbed controls`) per `<GEO_ID>`, a set of `perturbed controls` per `<GEO_ID>` to evaluate the gradient, or both.
Derivative-free methods can have several function evaluations per `<GEO_ID>` and no `perturbed controls`.
**NOTE:** the optimizer may decide that some `<GEO_ID>` are not needed, these are then skipped and the mapping from `ropt`
should reflect this (i.e., less `<GEO_ID>` in the batch results than expected).

.. figure:: images/Everest_vs_Ert_03.png
    :align: center
    :width: 700px
    :alt: Other `batch` configurations EVEREST

    Three other possible configurations of EVEREST `batches` in the context of gradient-based (i.e., `optpp_q_newton`)
    and gradient-free (i.e., **WHICH ONE DO WE SUPPORT?**) optimization algorithms.
