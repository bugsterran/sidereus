// Wrapper: spawns the script given as its first argument.
require("child_process").spawnSync(process.execPath, [process.argv[2]], { stdio: "inherit" });
