# Leadership and promise-deadline playtest

Tested main042d86d, game0.0.1, browser8479, copied TeamNexus26UHC seed2038,
W9 toW10. Root model and effort unknown/not exposed. Nine prelogged observations
(5met,2partial,1blocked,1unexpected). Original W9 fixture remained unchanged;
all543 source/test/data raw hashes stayed frozen. User8421 was untouched.

The player question was how to handle a new press decision and an approaching
play-time promise. Both LockerRoom and Echo profile showed Target60/Dressed5weeks
with oneweekleft but no units or evaluation-window denominator. The handbook
did not resolve this. New gap22 has its own explicitgpt-6.1-sol/medium agent.
Screenshots and public DOM evidence preserve the natural case.

Chose Slyblade's team-first press answer; actual flavor_event POST200 cleared
the pending event without advancing. Feedback said the safe answer disappeared
into the media cycle. The response observer watched a wrong route and timedout;
the actual request and response were recovered without repeating the decision.

Swapped Echo into the defaultfive for Hollowlock (condition43), keeping allsix
players. Immediate public readback verified exactly Apex,Vortex,Ghost,Slyblade,
Echo. One advance returned200: Nexus beatNordicFrost13-4, reportEcho1map and
Hollowlock0maps. Settled income68642-expenses47100 equals21542 bankincrease from
461864 to483406. W10 LockerRoom movedEcho toKEPT; explicitSave200 and reload
preserved bank/five/history. Original UI failure to locate Squad controls while
LockerRoom remained active was blocked before any mutation. Report-modal
navigation failed until Continue closed the overlay; no extra advance occurred.

Post-play raw-save readback verified Echo's existing promiseID unchanged,
active->kept, dressed5->6, target60 and initialduration8 preserved. This is an
observed outcome, not a counterfactual claim that this last appearance was
required. Apex remainsactive/dressed6/oneweekleft; Vortexactive/dressed4/fourleft.

## Quantitative coverage and limits

Three accepted decisions append to43 unchanged baseline actions: index43
flavor_choice(team_first/exactevent),44set_lineup(operationflags),45advance,
allweb/team_nexus/S1W9. Weekly snapshotprefix8->9 is unchanged. Accepted
operation coverage is3/3. Current set_lineup telemetry omits exactIDs; these are
verified separately from public and savedlineup, and existingPR361 owns the
instrumentation fix. Exact-choice coverage must not be claimed as3/3.

81 retained usageevents in two page sessions:14views54visible_time4attempts
4results1full_report_open2starts2ends. Requests23flavor_event,35lineup,37advance,
44Save each have one success200 result:4/4 pairs, no unmatchedattempts/orphans.
Cancelled/stale-locator attempts have no inferred HTTP rejection. Offline audits
and direct public fetches bypass browser wrapper instrumentation. Views cover
screen/subtab navigation; profile/handbook inspections lack separately identified
view events in this retained stream. Visible time remains a best-effort proxy,
not attention. Report command exits both0; supporting indexedledger andrequest
pairs are in evidence. Browserclosed; only own8479 family5508/20336/29168 verified
and stopped. Pre/post flywheel evidence retained; no simulatedstate was edited.

A later offline correction (step9) establishes Save request44 from the raw
usage stream. The preliminary row7 annotation and report guessed45; the old
row remains intact, and this correction identifies the actual retained pair.
