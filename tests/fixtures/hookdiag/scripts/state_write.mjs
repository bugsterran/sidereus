import { writeFileSync } from "fs";
writeFileSync("/tmp/x", JSON.stringify({ blockCount: 1 }));
console.log(JSON.stringify({ continue: true, suppressOutput: true }));
