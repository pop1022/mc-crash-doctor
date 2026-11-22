# mc-crash-doctor in a container.
#
#   docker build -t mc-crash-doctor .
#   docker run --rm -v "$PWD:/work" mc-crash-doctor /work/crash-report.txt
#   docker run --rm -i mc-crash-doctor --stdin < crash-report.txt
#
# The image is the "no Python on this machine" path: a server admin on Windows
# with a bare Docker Desktop gets the same engine, offline, without installing
# anything. Nothing in the image talks to the network at run time.
FROM python:3.12-slim AS build

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY mcd ./mcd
RUN pip install --no-cache-dir --prefix=/install .


FROM python:3.12-slim

LABEL org.opencontainers.image.title="mc-crash-doctor" \
      org.opencontainers.image.description="Diagnose Minecraft crash reports: root cause, suspect mod, the fix." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/pop1022/mc-crash-doctor"

COPY --from=build /install /usr/local

# Non-root, no home directory to write into: the tool only reads the report it
# is given. --stdin and a mounted file are the two supported input paths.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin mcd
USER 10001
WORKDIR /work

ENTRYPOINT ["mc-crash-doctor"]
CMD ["--help"]
