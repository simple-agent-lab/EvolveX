"""Run the current checkout through Harbor and distill meta-agent feedback."""

from evolve.frozen import sdk
from library._shared.harbor import HarborRollout, validate_config

__all__ = ["HarborRollout", "validate_config"]


if __name__ == "__main__":
    sdk.main(HarborRollout, validate_config=validate_config)
