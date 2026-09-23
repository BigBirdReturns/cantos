# Build only on the authorized CPU seat. BASE_IMAGE digest is UNVERIFIED here.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN python -m pip install --no-cache-dir evalplus==0.3.1 \
    && python -m pip freeze > /evalplus-installed.txt
# Capture the resulting immutable local image ID in the prereg freeze packet.
# Runtime network is disabled by grade.sh; datasets are retained local overrides.
