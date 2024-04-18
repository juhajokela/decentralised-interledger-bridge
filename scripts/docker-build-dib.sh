# should be run from root directory of repository
export DOCKER_BUILDKIT=1
docker build -f docker/Dockerfile --target run_dib -t interledger-dib .
