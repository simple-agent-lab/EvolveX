"""Run the current checkout through Harbor and distill mutate feedback."""

from evolve.frozen import sdk
from library._shared.harbor import CONFIG, HarborRollout

__all__ = ["CONFIG", "HarborRollout"]


if __name__ == "__main__":
    sdk.main(HarborRollout, config_schema=CONFIG)
