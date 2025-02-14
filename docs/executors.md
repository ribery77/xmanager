# Executors

## Local

The local executor declares that an executable will be run on the same machine
from which the launch script is invoked.

```python
xm_local.Local(
    docker_options=xm_local.DockerOptions(...),
)
```

## Cloud AI Platform (CAIP)

The `Caip` executor declares that an executable will be run on the CAIP
platform.

The Caip executor takes in a resource requirements object.

```python
xm_local.Caip(
    xm.JobRequirements(
        cpu=1,  # Measured in vCPUs.
        ram=4 * xm.GiB,
        T4=1,  # NVIDIA Tesla T4.
    ),
)
```

```python
xm_local.Caip(
    xm.JobRequirements(
        cpu=1,  # Measured in vCPUs.
        ram=4 * xm.GiB,
        TPU_V2=8,  # TPU v2.
    ),
)
```

As of June 2021, the currently supported accelerator types are:

* `P100`
* `V100`
* `P4`
* `T4`
* `A100`
* `TPU_V2`
* `TPU_V3`

IMPORTANT: Note that for `TPU_V2` and `TPU_V3` the only currently supported
count is 8.

### Caip Specification

The CAIP executor allows you specify a remote image repository to push to.

```python
xm_local.Caip.Spec(
    push_image_tag='gcr.io/<project>/<image>:<tag>',
)
```

## Kubernetes (experimental)

The Kubernetes executor declares that an executable will be run on a Kubernetes
cluster. As of October 2021, Kubernetes is not fully supported.

The Kubernetes executor pulls from your local `kubeconfig`. The XManager
command-line has helpers to set up a Google Kubernetes Engine (GKE) cluster.

```bash
pip install caliban==0.4.1
xmanager cluster create

# cleanup
xmanager cluster delete
```

You can store the GKE credentials in your `kubeconfig`:

```bash
gcloud container clusters get-credentials <cluster-name>
```

### Kubernetes Specification

The Kubernetes executor allows you specify a remote image repository to push to.

```python
xm_local.Kubernetes.Spec(
    push_image_tag='gcr.io/<project>/<image>:<tag>',
)
```
