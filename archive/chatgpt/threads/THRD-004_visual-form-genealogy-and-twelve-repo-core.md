---
id: THRD-004
title: "Visual Form Canon Genealogy and Twelve-Repository Research Map"
date: 2026-09-05
tags: ["genealogy", "twelve-repositories", "persona-system", "ownership-boundaries", "copilot-planning"]
source: "chatgpt-responses--multiple-chats.txt (Lines 398-541)"
---

# Visual Form Canon Genealogy and Twelve-Repository Research Map

> **Unique ID**:   
> **Date**: 2026-09-05  
> **Tags**: , , , ,   
> **Source**: Extracted from ChatGPT conversation archive (, Lines 398–541)

## Summary & Significance
Maps the 12-repository core of the persona system (hospes, laurea, private, etc.), establishes provenance boundaries (Triptych vs Narcissus), defines the long-term research lineage, and plans the monthly Copilot assignment for declarative N-loop composition.

---

## Transcript Content

## Emerging genealogy

The corpus is becoming much more intelligible:

**First Circle (?)**
→ **Triptych / three-panel photo-selection form**
→ **Triptych Video Canon**
→ **Up the Hill Backwards / four-panel extension**
→ **Floating Points / dense multilayer and nested compositing**
→ **Danse / deterministic spatial-generative composition**
→ **common composition engine**
→ **generative audio + modulation**
→ **persistent public world**
→ **participatory/spatial/physical realization**

The middle of that genealogy is no longer theoretical. We now have actual production artifacts on both sides of it.

The next highest-value work is therefore **binary-project archaeology on Floating Points and Up the Hill Backwards plus the Portvs topology refactor**, rather than another broad repository search. I have already scoped the topology-refactor job on issue #8 so the Copilot allowance can be spent on implementation rather than rediscovery.
Yes. **Most of that work is work I can do directly here against the connected GitHub corpus.**

I can inspect repositories and their histories, trace the lineage among **Floating Points → First Circle/Triptych → Up the Hill Backwards → Danse/The Thing With No Name → current persona/audiovisual system**, inspect implementations and documentation, compare architectures, locate duplicated or displaced material, distinguish working code from conceptual claims, and construct the cross-repository research corpus.

I can also **modify GitHub directly**: create/update files, branches, issues, PRs, documentation, manifests, schemas, and implementation work through the connected GitHub tooling. So we do **not** need to spend your Copilot allowance merely having Copilot perform repository research that I can already perform.

The distinction is:

- **I should do the corpus archaeology, synthesis, architecture, planning, and GitHub coordination here.**
- **Copilot should be reserved for work where its cloud coding environment gives us leverage**—larger implementation/test/build tasks inside individual repositories, especially when it can autonomously work a branch and run the repository.
- Anything requiring media that exists **only on your inaccessible Mac**, local Ableton/TouchDesigner/Adobe files, hardware, or an unpushed local repository remains inaccessible until that material reaches a remote source.

So my previous recommendation to make the **first Copilot assignment a research pass was unnecessarily wasteful**. I can do that research myself.

The better sequence is **I perform the complete cross-repository archaeological audit now, establish the canonical lineage and capability map, identify exact implementation gaps, and only then allocate Copilot tokens to the highest-value executable jobs that emerge from the audit.**
**I recommend twelve repositories as the initial working corpus, with eleven more for long-range research, preservation, publishing, and performance support.** Your estimate is right for a manageable core—but the wider project reaches beyond ten.

I checked live GitHub metadata, selected project documents, and file trees. **This identifies where the work lives; it does not certify that every documented feature builds or runs.** No repositories were modified and no Copilot session was launched.

:chatgpt-content-reference{index="31"} — annotated repository map, machine-readable registry, and a ready-to-paste Copilot research assignment.

## 1. The twelve-repository working core

The IDs below are assigned for this inventory. The downloadable registry also preserves GitHub’s numerical repository IDs, so renamed or transferred repositories can be tracked.

| ID | Repository | Why it belongs |
|---|---|---|
| **PER-GH-001** | **[organvm/portvs](https://github.com/organvm/portvs)** | **Existing audiovisual research and lineage workspace.** The directory `incubator/triptych-video-canon/` contains the Triptych project, Visual Form Canon, unification notes, and prior research. This is the strongest starting point for connecting earlier works to the evolving system—not a reason to rebuild those works from scratch.  |
| **PER-GH-002** | **[organvm/the-thing-without-a-name](https://github.com/organvm/the-thing-without-a-name)** | **Danse: photographic material becoming a generative audiovisual environment.** Its composition, temporal behavior, interaction, and capture machinery are directly relevant to the layered-image direction. The current README explicitly distinguishes the browser artwork from the broader project package, which remains draft with unresolved gates.  |
| **PER-GH-003** | **[organvm-ii-poiesis/a-mavs-olevm](https://github.com/organvm-ii-poiesis/a-mavs-olevm)** | **The creative website as an artwork.** This is the ET CETER4/Pantheon source: music, writing, visual work, generative elements, and nonlinear chambers. It is particularly relevant to your continuously evolving website-artifact—not merely a promotional site containing links to the real work.  |
| **PER-GH-004** | **[organvm/alchemical-synthesizer](https://github.com/organvm/alchemical-synthesizer)** | **Audio, audiovisual production, and continuous broadcast.** It houses **Brahma**, the synthesizer and Visual Cortex; **Forge**, the track-and-visual production lane; and **AETHER**, the living-radio streaming lane. Those are three components inside one repository, not three separately verified repositories.  |
| **PER-GH-005** | **[organvm/metasystem-master](https://github.com/organvm/metasystem-master)** | **Omni-Dromenon’s participatory performance system.** The documented architecture connects audience input, performance parameters, consensus, performer override, and an OSC bridge. This belongs wherever the project becomes a live instrument or audience-responsive event.  |
| **PER-GH-006** | **[organvm/generative-abstract-environments-studies](https://github.com/organvm/generative-abstract-environments-studies)** — private | **Browser visualizer research.** Portvs identifies this as the home of HTML/canvas studies such as Confluence and related generative environments; I also verified its current source-file collection. It is an experimental visual corpus, not simply a proposal for a future visualizer. Current runtime behavior still needs checking.  |
| **PER-GH-007** | **[organvm-iii-ergon/glyph-cascade](https://github.com/organvm-iii-ergon/glyph-cascade)** | **Text becoming audiovisual form.** The current repository describes a React/Vite/Tailwind/Tone.js frontend for generative audiovisual exploration. The older `organvm/glyph-cascade` address now resolves to this owner; we should not perpetuate the old location or assume the old build findings remain current.  |
| **PER-GH-008** | **[organvm/glyph-cascade-tapes](https://github.com/organvm/glyph-cascade-tapes)** — private | **The related cyberpoetry experiments and iteration history.** Its tree contains `CyberpoetryIterationCinema`, `CyberpoetryIterationLab`, several `CyberpoetryReactor` variants, `MatrixCascade`, specifications, and archive material. This is distinct from the preceding frontend repository and deserves a lineage comparison rather than an automatic merge.  |
| **PER-GH-009** | **[organvm/linguistic-atomization-framework](https://github.com/organvm/linguistic-atomization-framework)** | **Language as structured, transformable material.** LingFrame’s hierarchy—theme, paragraph, sentence, word, letter—connects directly to your atomization and modular-transformation research. Its role is an analysis instrument, not merely a caption generator.  |
| **PER-GH-010** | **[organvm/media-ark](https://github.com/organvm/media-ark)** | **Source custody and retrieval.** This supplies the documented ingestion, deduplication, sidecar metadata, indexing, and repair model. It matters because the creative system needs identifiable, recoverable source material—not just a large folder of media. Repository access does **not** establish that your actual photo/video archives are present remotely.  |
| **PER-GH-011** | **[organvm/vox--architectura-gubernatio](https://github.com/organvm/vox--architectura-gubernatio)** — private | **Research into your authorial voice.** It contains documented corpus-backed scoring, editable stylistic parameters, and editorial workflows. I would use it to study patterns in your actual language, not let its existing institutional scoring rules dictate how you speak publicly.  |
| **PER-GH-012** | **[4444J99/content-engine--asset-amplifier](https://github.com/4444J99/content-engine--asset-amplifier)** — private | **Reusable production machinery.** Cronus Metabolus describes ingestion, extraction, clips, derivatives, and distribution. The opportunity is to reuse suitable processing capabilities—not inherit its premium-brand marketing brief, generic captioning assumptions, or partner-specific material.  |

**This is not twelve projects to activate simultaneously.** It is twelve places where existing material or capabilities could materially reduce the work required.

## 2. The longer research lineage

These five should remain inside the research scope even when they are not the next implementation target.

| ID | Repository | Research relationship |
|---|---|---|
| **PER-GH-013** | **[organvm-ii-poiesis/ivi374ivi027-05](https://github.com/organvm-ii-poiesis/ivi374ivi027-05)** | **MET4MORFOSES Web Edition.** Its map, faux-social-feed, scroll, reader, and archive modes connect literary work to nonlinear interfaces. This is an important bridge between the earlier writing and the present multimedia practice.  |
| **PER-GH-014** | **[organvm/collective-persona-operations](https://github.com/organvm/collective-persona-operations)** | **Identity across contexts and registers.** Relevant theoretical material, but the inspected document contains planned architecture. It should inform questions about persona—not be mistaken for an already functioning public-life operating system.  |
| **PER-GH-015** | **[organvm-ii-poiesis/narratological-algorithmic-lenses](https://github.com/organvm-ii-poiesis/narratological-algorithmic-lenses)** | **Comparative narrative and craft research.** Its research corpus spans film, games, classical traditions, Pixar, and comedy. Useful for interpreting and editing material without requiring you to script your life or repeat rehearsed performances.  |
| **PER-GH-016** | **[organvm/recursive-engine--generative-entity](https://github.com/organvm/recursive-engine--generative-entity)** | **Memory, recurrence, myth, and transformation.** RE:GE’s fragment and significance models are relevant to how motifs recur across your work and acquire meaning. The conceptual claims and implemented mechanisms need separate evaluation.  |
| **PER-GH-017** | **[organvm-ii-poiesis/archive-past-works](https://github.com/organvm-ii-poiesis/archive-past-works)** | **Historical preservation and provenance.** Its documented purpose is preservation rather than public presentation. It belongs in the lineage investigation, but its existence is not proof that every earlier artwork or source file has already been recovered.  |

For this project, “long-ranging” should mean investigating **how the work changes across years, media, interfaces, and audiences**—not simply expanding the software stack.

The recurring research object can be:

**Original material → transformation rules → instrument or environment → performance → captured edition → public expression → preserved record.**

The existing Visual Form Canon already gives us a useful comparison structure: source set, visual grammar, runtime target, remix transformations, public/private boundary, and eventual implementation owner. 

## 3. Publishing and performance support

These six are relevant infrastructure, but they should not determine the creative identity.

| ID | Repository | Appropriate role |
|---|---|---|
| **PER-GH-018** | **[organvm-iii-ergon/multi-camera--livestream--framework](https://github.com/organvm-iii-ergon/multi-camera--livestream--framework)** | Capture, camera/audio coordination, and streaming procedures. Its hardware-dependent requirements need separating from what can be prepared or tested remotely now.  |
| **PER-GH-019** | **[organvm-vii-kerygma/showcase-portfolio](https://github.com/organvm-vii-kerygma/showcase-portfolio)** | Artistic and curatorial presentation: works, process, installations, and exhibition-facing context.  |
| **PER-GH-020** | **[organvm-vii-kerygma/portfolio](https://github.com/organvm-vii-kerygma/portfolio)** | The general professional case-study gateway. Relevant, but it should remain distinguishable from the public-life project and its broader audience.  |
| **PER-GH-021** | **[organvm-iv-taxis/distribution-strategy](https://github.com/organvm-iv-taxis/distribution-strategy)** | Existing audience/channel research. Its stated goals emphasize grants, hiring, and institutional visibility; those are not interchangeable with this project’s public-life and community goals.  |
| **PER-GH-022** | **[organvm/social-automation](https://github.com/organvm/social-automation)** | Candidate scheduling, channel-adapter, retry, delivery-receipt, and analytics infrastructure. Actual adapter coverage and approval behavior need inspection before adoption.  |
| **PER-GH-023** | **[organvm/kerygma-pipeline](https://github.com/organvm/kerygma-pipeline)** | Distribution orchestration candidate. Its root README identifies that purpose, but is too brief to establish an operational end-to-end system.  |

There are also two useful **separate partner references**: [new-ancients-social](https://github.com/4444J99/new-ancients-social), for musician-specific approval and source-linked voice patterns, and [post-dsp-platform](https://github.com/4444J99/post-dsp-platform), for longer-horizon artist infrastructure. Neither should be relabeled as your persona project, and neither partner’s content should become your voice corpus. The latter explicitly documents that consumer playback, UI, and live delivery are not built. 

## 4. Important ownership and evidence distinctions

### Triptych is located; several original-work mappings remain unresolved

The Triptych project is in:

`organvm/portvs/incubator/triptych-video-canon/`

Its July posting packet describes the earlier moving-image work and a three-panel instrument. It also names media files through **local Mac paths**. Those references do not mean a remote agent possesses the media. 

I have **not yet independently established** the exact source-file mapping connecting The First Circle to the present selector, or the dedicated repository/file locations for **Floating Points** and **Up the Hill Backwards**. These are unresolved lineage questions—not evidence that the work is missing, and not justification for inventing replacement repositories.

### The visual research already has a coordination home

Portvs’s existing protocol says to keep the incubation work in its current directory, leave final implementation ownership unresolved until established, and avoid modifying Limen, `config/_limen`, `graph.jsonl`, or adjacent implementation repositories during that pass. **I would preserve that separation rather than create a new persona monorepo.** 

That makes Portvs the starting point for **this audiovisual lineage investigation**, not automatically the permanent home of every public-life decision.

### A matching name is not enough

`organvm/persona-fleet` is **not** the project’s home. Its README explicitly excludes the operator’s identity, brand, audience, and network. The registry marks it as a false lead so it is not repeatedly rediscovered. 

The downloadable registry similarly distinguishes archived counterparts and metadata-only candidates from repositories whose contents I inspected.

## 5. How to use the monthly Copilot allowance

**The remote approach is viable, but it should be repository-by-repository.**

GitHub’s current individual-plan documentation says included **AI credits reset at 00:00 UTC on the first day of each calendar month**, do not roll over, and are consumed according to model and token usage. Your actual balance and plan were not inspected here. 

Copilot’s cloud agent supports repository research and planning on GitHub.com before a pull request is created. It also consumes **GitHub Actions minutes**. By default, its context is limited to the selected repository, and it can modify only that repository in a run; broader reading requires appropriate access configuration. Our GitHub connector access here does not establish that Copilot has identical access. 

I would use the allowance in three stages:

1. **Recover the evidence.** Begin with Portvs: exact work titles, original/derivative relationships, source locations, implemented renderers, and unresolved ownership. Do not begin by rewriting code.
2. **Inspect reusable mechanisms.** Give individual repositories bounded tasks concerning panel selection, timing, seeded variation, text transformations, audio modulation, capture, or voice provenance. Each result should identify actual files and verification gaps.
3. **Implement one demonstrated need at a time.** Only then commission a narrowly scoped change in the correct repository, with an acceptance test and explicit publication boundaries.

The economical unit is **a resolved question or verified capability**, not another long generated document. A compact evidence report can be reused across sessions; repeatedly loading the entire history into every agent would work against the monthly allowance.

### First assignment

**Start in `organvm/portvs` and reconcile the existing Triptych/Visual Form Canon with the named earlier works.** The supplied prompt requests research only, records missing remote assets, separates historical claims from current verification, and prohibits adjacent-repository mutations.

:chatgpt-content-reference{index="32"} · :chatgpt-content-reference{index="33"} · :chatgpt-content-reference{index="34"}

**The direction is broad research with bounded execution: recover the relationships across the existing corpus, then spend implementation effort where that evidence identifies a real gap.**
Execution has begun from the handoff rather than restarting planning.
