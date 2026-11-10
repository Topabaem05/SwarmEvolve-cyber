--- shinka-convert ---

# SkillSpector Security Report

**Skill:** shinka\-convert  
**Source:** `/home/user/SwarmEvolve-cyber/baselines/ShinkaEvolve/skills/shinka-convert`  
**Scanned:** 2026-11-10 06:28:26 UTC  

## Risk Assessment

| Metric | Value |
|--------|-------|
| Score | 14/100 |
| Severity | LOW |
| Recommendation | SAFE |

## Components (3)

| File | Type | Lines | Executable |
|------|------|-------|------------|
| `SKILL.md` | markdown | 170 | No |
| `scripts/run_evo.py` | python | 44 | Yes |
| `scripts/shinka.yaml` | yaml | 48 | No |

## Issues (2)

### 🟡 MEDIUM: LP3

**Location:** `SKILL.md:1`  
**Confidence:** 70%  

**Message:** Skill declares no tool scope \('permissions' or 'allowed\-tools'\) but code capabilities were detected: file\_read\.

**Remediation:** Clarify the skill's intended tool scope and review how the host runtime enforces it; runtime permissions are unknown unless separately verified\. For Claude Code / Agent Skills SKILL\.md, 'allowed\-tools' records preapproved tools, not a permission ceiling; add a tool only when it is independently approved as necessary, not to silence this finding\. For MCP server manifests, use a 'permissions' list naming the required capabilities\.

---

### 🟡 MEDIUM: EA2

**Location:** `SKILL.md:59`  
**Confidence:** 75%  

**Message:** Autonomous Decision Making

**Remediation:** Add human\-in\-the\-loop confirmation for destructive, irreversible, or high\-impact operations\. Never auto\-execute commands that modify files, send data, or alter system state\.

---

## Inspection Completeness

| Metric | Value |
|--------|-------|
| Execution | successful |
| Status | complete\_with\_caveats |
| Dependency contents | not\_requested |
| Coverage | 100\.0% |
| Fully inspected | 3 |
| Partially inspected | 0 |
| Entirely uninspected | 0 |

### Ledger Exceptions

| Reason / Status | Location | Details |
|-----------------|----------|---------|
| reference\_missing | `SKILL.md:3-3` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:18-18` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:23-23` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:39-39` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:67-67` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:87-87` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:88-88` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:140-140` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:158-158` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:159-159` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |

### Analyzer Statuses

| Reason / Status | Location | Details |
|-----------------|----------|---------|
| completed | `artifact_integrity` |  |
| completed | `behavioral_ast` |  |
| completed | `behavioral_taint_tracking` |  |
| no\_applicable\_files | `bundled_execution_surface` | No files matched this analyzer's applicability contract\. |
| completed | `mcp_least_privilege` |  |
| completed | `mcp_rug_pull` |  |
| completed | `mcp_tool_poisoning` |  |
| disabled\_by\_configuration | `meta_analyzer` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_developer_intent` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_quality_policy` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_security_discovery` | Analyzer was disabled by the requested configuration\. |
| completed | `static_patterns_agent_snooping` |  |
| completed | `static_patterns_anti_refusal` |  |
| completed | `static_patterns_data_exfiltration` |  |
| completed | `static_patterns_deserialization` |  |
| completed | `static_patterns_excessive_agency` |  |
| completed | `static_patterns_harmful_content` |  |
| completed | `static_patterns_memory_poisoning` |  |
| completed | `static_patterns_output_handling` |  |
| completed | `static_patterns_privilege_escalation` |  |
| completed | `static_patterns_prompt_injection` |  |
| completed | `static_patterns_rogue_agent` |  |
| completed | `static_patterns_ssrf` |  |
| completed | `static_patterns_supply_chain` |  |
| completed | `static_patterns_system_prompt_leakage` |  |
| completed | `static_patterns_tool_misuse` |  |
| completed | `static_yara` |  |

## Metadata

- **Executable Scripts:** Yes

*Generated by SkillSpector v2.12.0*

--- shinka-inspect ---

# SkillSpector Security Report

**Skill:** shinka\-inspect  
**Source:** `/home/user/SwarmEvolve-cyber/baselines/ShinkaEvolve/skills/shinka-inspect`  
**Scanned:** 2026-11-10 06:28:27 UTC  

## Risk Assessment

| Metric | Value |
|--------|-------|
| Score | 7/100 |
| Severity | LOW |
| Recommendation | SAFE |

## Components (2)

| File | Type | Lines | Executable |
|------|------|-------|------------|
| `SKILL.md` | markdown | 63 | No |
| `scripts/inspect_best_programs.py` | python | 326 | Yes |

## Issues (1)

### 🟡 MEDIUM: LP3

**Location:** `SKILL.md:1`  
**Confidence:** 70%  

**Message:** Skill declares no tool scope \('permissions' or 'allowed\-tools'\) but code capabilities were detected: file\_write\.

**Remediation:** Clarify the skill's intended tool scope and review how the host runtime enforces it; runtime permissions are unknown unless separately verified\. For Claude Code / Agent Skills SKILL\.md, 'allowed\-tools' records preapproved tools, not a permission ceiling; add a tool only when it is independently approved as necessary, not to silence this finding\. For MCP server manifests, use a 'permissions' list naming the required capabilities\.

---

## Inspection Completeness

| Metric | Value |
|--------|-------|
| Execution | successful |
| Status | complete\_with\_caveats |
| Dependency contents | not\_requested |
| Coverage | 100\.0% |
| Fully inspected | 2 |
| Partially inspected | 0 |
| Entirely uninspected | 0 |

### Ledger Exceptions

| Reason / Status | Location | Details |
|-----------------|----------|---------|
| reference\_missing | `SKILL.md:33-33` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:40-40` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |

### Analyzer Statuses

| Reason / Status | Location | Details |
|-----------------|----------|---------|
| completed | `artifact_integrity` |  |
| completed | `behavioral_ast` |  |
| completed | `behavioral_taint_tracking` |  |
| no\_applicable\_files | `bundled_execution_surface` | No files matched this analyzer's applicability contract\. |
| completed | `mcp_least_privilege` |  |
| completed | `mcp_rug_pull` |  |
| completed | `mcp_tool_poisoning` |  |
| disabled\_by\_configuration | `meta_analyzer` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_developer_intent` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_quality_policy` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_security_discovery` | Analyzer was disabled by the requested configuration\. |
| completed | `static_patterns_agent_snooping` |  |
| completed | `static_patterns_anti_refusal` |  |
| completed | `static_patterns_data_exfiltration` |  |
| completed | `static_patterns_deserialization` |  |
| completed | `static_patterns_excessive_agency` |  |
| completed | `static_patterns_harmful_content` |  |
| completed | `static_patterns_memory_poisoning` |  |
| completed | `static_patterns_output_handling` |  |
| completed | `static_patterns_privilege_escalation` |  |
| completed | `static_patterns_prompt_injection` |  |
| completed | `static_patterns_rogue_agent` |  |
| completed | `static_patterns_ssrf` |  |
| completed | `static_patterns_supply_chain` |  |
| completed | `static_patterns_system_prompt_leakage` |  |
| completed | `static_patterns_tool_misuse` |  |
| completed | `static_yara` |  |

## Metadata

- **Executable Scripts:** Yes

*Generated by SkillSpector v2.12.0*

--- shinka-run ---

# SkillSpector Security Report

**Skill:** shinka\-run  
**Source:** `/home/user/SwarmEvolve-cyber/baselines/ShinkaEvolve/skills/shinka-run`  
**Scanned:** 2026-11-10 06:28:27 UTC  

## Risk Assessment

| Metric | Value |
|--------|-------|
| Score | 0/100 |
| Severity | LOW |
| Recommendation | SAFE |

## Components (1)

| File | Type | Lines | Executable |
|------|------|-------|------------|
| `SKILL.md` | markdown | 113 | No |

## Issues (0)

No security issues detected.

## Inspection Completeness

| Metric | Value |
|--------|-------|
| Execution | successful |
| Status | complete\_with\_caveats |
| Dependency contents | not\_requested |
| Coverage | 100\.0% |
| Fully inspected | 1 |
| Partially inspected | 0 |
| Entirely uninspected | 0 |

### Ledger Exceptions

| Reason / Status | Location | Details |
|-----------------|----------|---------|
| reference\_missing | `SKILL.md:3-3` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:11-11` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:30-30` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |

### Analyzer Statuses

| Reason / Status | Location | Details |
|-----------------|----------|---------|
| completed | `artifact_integrity` |  |
| no\_applicable\_files | `behavioral_ast` | No files matched this analyzer's applicability contract\. |
| no\_applicable\_files | `behavioral_taint_tracking` | No files matched this analyzer's applicability contract\. |
| no\_applicable\_files | `bundled_execution_surface` | No files matched this analyzer's applicability contract\. |
| no\_applicable\_files | `mcp_least_privilege` | No files matched this analyzer's applicability contract\. |
| completed | `mcp_rug_pull` |  |
| completed | `mcp_tool_poisoning` |  |
| no\_applicable\_files | `meta_analyzer` | No files matched this analyzer's applicability contract\. |
| disabled\_by\_configuration | `semantic_developer_intent` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_quality_policy` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_security_discovery` | Analyzer was disabled by the requested configuration\. |
| completed | `static_patterns_agent_snooping` |  |
| completed | `static_patterns_anti_refusal` |  |
| completed | `static_patterns_data_exfiltration` |  |
| completed | `static_patterns_deserialization` |  |
| completed | `static_patterns_excessive_agency` |  |
| completed | `static_patterns_harmful_content` |  |
| completed | `static_patterns_memory_poisoning` |  |
| completed | `static_patterns_output_handling` |  |
| completed | `static_patterns_privilege_escalation` |  |
| completed | `static_patterns_prompt_injection` |  |
| completed | `static_patterns_rogue_agent` |  |
| completed | `static_patterns_ssrf` |  |
| completed | `static_patterns_supply_chain` |  |
| completed | `static_patterns_system_prompt_leakage` |  |
| completed | `static_patterns_tool_misuse` |  |
| completed | `static_yara` |  |

## Metadata

- **Executable Scripts:** No

*Generated by SkillSpector v2.12.0*

--- shinka-setup ---

# SkillSpector Security Report

**Skill:** shinka\-setup  
**Source:** `/home/user/SwarmEvolve-cyber/baselines/ShinkaEvolve/skills/shinka-setup`  
**Scanned:** 2026-11-10 06:28:28 UTC  

## Risk Assessment

| Metric | Value |
|--------|-------|
| Score | 14/100 |
| Severity | LOW |
| Recommendation | SAFE |

## Components (3)

| File | Type | Lines | Executable |
|------|------|-------|------------|
| `SKILL.md` | markdown | 232 | No |
| `scripts/run_evo.py` | python | 42 | Yes |
| `scripts/shinka.yaml` | yaml | 48 | No |

## Issues (2)

### 🟡 MEDIUM: LP3

**Location:** `SKILL.md:1`  
**Confidence:** 70%  

**Message:** Skill declares no tool scope \('permissions' or 'allowed\-tools'\) but code capabilities were detected: file\_read\.

**Remediation:** Clarify the skill's intended tool scope and review how the host runtime enforces it; runtime permissions are unknown unless separately verified\. For Claude Code / Agent Skills SKILL\.md, 'allowed\-tools' records preapproved tools, not a permission ceiling; add a tool only when it is independently approved as necessary, not to silence this finding\. For MCP server manifests, use a 'permissions' list naming the required capabilities\.

---

### 🟡 MEDIUM: EA2

**Location:** `SKILL.md:25`  
**Confidence:** 75%  

**Message:** Autonomous Decision Making

**Remediation:** Add human\-in\-the\-loop confirmation for destructive, irreversible, or high\-impact operations\. Never auto\-execute commands that modify files, send data, or alter system state\.

---

## Inspection Completeness

| Metric | Value |
|--------|-------|
| Execution | successful |
| Status | complete\_with\_caveats |
| Dependency contents | not\_requested |
| Coverage | 100\.0% |
| Fully inspected | 3 |
| Partially inspected | 0 |
| Entirely uninspected | 0 |

### Ledger Exceptions

| Reason / Status | Location | Details |
|-----------------|----------|---------|
| reference\_missing | `SKILL.md:3-3` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:12-12` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:25-25` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:27-27` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:28-28` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:29-29` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:31-31` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:35-35` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:41-41` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:64-64` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:85-85` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:87-87` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:88-88` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:89-89` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:90-90` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:91-91` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:92-92` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:93-93` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:94-94` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:97-97` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:99-99` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:100-100` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:124-124` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:126-126` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:180-180` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:203-203` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:206-206` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:221-221` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:225-225` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |
| reference\_missing | `SKILL.md:230-230` | A local path\-like reference does not match any bundled artifact, such as a file the skill writes at runtime\. |

### Analyzer Statuses

| Reason / Status | Location | Details |
|-----------------|----------|---------|
| completed | `artifact_integrity` |  |
| completed | `behavioral_ast` |  |
| completed | `behavioral_taint_tracking` |  |
| no\_applicable\_files | `bundled_execution_surface` | No files matched this analyzer's applicability contract\. |
| completed | `mcp_least_privilege` |  |
| completed | `mcp_rug_pull` |  |
| completed | `mcp_tool_poisoning` |  |
| disabled\_by\_configuration | `meta_analyzer` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_developer_intent` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_quality_policy` | Analyzer was disabled by the requested configuration\. |
| disabled\_by\_configuration | `semantic_security_discovery` | Analyzer was disabled by the requested configuration\. |
| completed | `static_patterns_agent_snooping` |  |
| completed | `static_patterns_anti_refusal` |  |
| completed | `static_patterns_data_exfiltration` |  |
| completed | `static_patterns_deserialization` |  |
| completed | `static_patterns_excessive_agency` |  |
| completed | `static_patterns_harmful_content` |  |
| completed | `static_patterns_memory_poisoning` |  |
| completed | `static_patterns_output_handling` |  |
| completed | `static_patterns_privilege_escalation` |  |
| completed | `static_patterns_prompt_injection` |  |
| completed | `static_patterns_rogue_agent` |  |
| completed | `static_patterns_ssrf` |  |
| completed | `static_patterns_supply_chain` |  |
| completed | `static_patterns_system_prompt_leakage` |  |
| completed | `static_patterns_tool_misuse` |  |
| completed | `static_yara` |  |

## Metadata

- **Executable Scripts:** Yes

*Generated by SkillSpector v2.12.0*