Set-Location "F:\Documents\GitHub\OpenBuildCore"
git init -b main | Out-Null
git add -A
git commit -m "OpenBuildCore: inventory-driven build advisor" -m "Fourth Open*Core peer (ADR-0001): what you own, and what you could make of it. Requirements are specific parts or capabilities with quantities; allocation is exclusive so one unit satisfies at most one requirement - the case Oh-Ben-Claw's presence-only planner gets wrong. Suggestions are found by searching OpenPartsCore rather than from hardcoded lists (ADR-0002). Three seed projects, example inventory, 8 stdlib tests." | Select-Object -First 1
gh repo create thewriterben/OpenBuildCore --public --source . --push --description "Tell it what you own; it tells you what you can build and what you are missing. Fourth peer of the OpenDesignCore platform."
