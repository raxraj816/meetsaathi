# Build with --build-arg ADOT_IMAGE=<reviewed public.ecr.aws/aws-observability/aws-otel-collector@sha256:...>
ARG ADOT_IMAGE
FROM ${ADOT_IMAGE}
COPY collector.yaml /etc/meetsaathi/collector.yaml
