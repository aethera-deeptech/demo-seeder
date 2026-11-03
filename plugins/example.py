"""An example plugin. Files in this folder are loaded when the seeder starts, and a file that starts with an underscore is skipped.

Copy this file, change the class, and name the profile in the `profile` setting of a device. Delete this file if you do not want it.
"""

from seeder.profiles import Profile, Reading
from seeder.registry import profile


@profile("night-shift")
class NightShift(Profile):
    """A machine that works from 20:00 to 04:00. Params are on_watts and standby_watts."""

    def sample(self, ctx):
        working = ctx.hour >= 20 or ctx.hour < 4
        if working:
            return Reading(self.noisy(self.number("on_watts", 400), 0.05))
        return Reading(self.noisy(self.number("standby_watts", 4), 0.1), None, 1)
