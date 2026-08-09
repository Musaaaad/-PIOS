window.PIOS_DEMO = {
  notice: "بيانات عرض تجريبية غير معتمدة - لا تمثل جاهزية مستشفى طريف الفعلية",
  identity: {user_id:"demo-user", display_name:"قائد الاعتماد", roles:["AccreditationLead","MedicationSafety"], auth_source:"demo"},
  overview: {
    site:{code:"TGH",name_ar:"مستشفى طريف العام",name_en:"Turaif General Hospital"},
    readiness:{snapshot_id:"demo",period_label:"Pilot Baseline",score:42,overall_status:"CriticalOpenActions",critical_open_actions:true,accepted:86,partial:52,missing:128,esr_status:{"MM.5":"Red","MM.6":"Amber","MM.41":"Red"}},
    findings:{open_total:31,by_severity:{P0:8,P1:15,P2:8}},
    capas:{by_status:{Draft:5,Submitted:3,Approved:4,InProgress:7,EffectivenessPending:2,Closed:9},overdue:6},
    evidence:{overdue_requests:18,under_review:24},
    documents:{Draft:22,Review:6,Approved:9,Effective:38},
    notifications:{unread:12,critical:4},
    generated_at:new Date().toISOString()
  },
  standards: Array.from({length:41},(_,i)=>({
    standard:`MM.${i+1}`,
    total: i===0?2:(i===4?4:(i===40?12:Math.max(3,Math.round(266/41)))),
    states: i===4?{CriticalBlocked:2,EvidenceReady:1,Missing:1}:i===5?{Blocked:2,EvidenceReady:1}:i===40?{CriticalBlocked:4,Partial:3,Missing:5}:{EvidenceReady:(i%4)+1,Partial:(i%3),Missing:(i%5)}
  })),
  worklist: [
    {task_type:"Finding",id:"f1",title:"P0 - MM.5.3",status:"CAPAOpen",severity:"Critical",due_at:"2026-08-02",href:"#/findings/f1"},
    {task_type:"Finding",id:"f2",title:"P0 - MM.41.8",status:"Open",severity:"Critical",due_at:"2026-08-03",href:"#/findings/f2"},
    {task_type:"EvidenceRequest",id:"e1",title:"دليل MM.20.3 - OMR",status:"Requested",severity:"Warning",due_at:"2026-07-30",href:"#/evidence/e1"},
    {task_type:"CAPA",id:"c1",title:"CAPA MM.12.7: انحراف حراري",status:"InProgress",severity:"P1",due_at:"2026-08-05",href:"#/capas/c1"},
    {task_type:"EvidenceRequest",id:"e2",title:"دليل MM.31.7 - Observation",status:"Submitted",severity:"Normal",due_at:"2026-08-09",href:"#/evidence/e2"},
    {task_type:"CAPA",id:"c2",title:"CAPA MM.6.3: LASA Tracer",status:"EffectivenessPending",severity:"Critical",due_at:"2026-08-04",href:"#/capas/c2"}
  ],
  notifications:[
    {id:"n1",category:"Finding",severity:"Critical",title:"P0 مفتوح على MM.41.8",message:"RCA للحادثة المهمة لم يكتمل.",status:"Unread",created_at:new Date().toISOString(),action_url:"#/findings/f2"},
    {id:"n2",category:"CAPA",severity:"Warning",title:"CAPA متأخرة",message:"حزمة الانحراف الحراري تجاوزت الموعد.",status:"Unread",created_at:new Date().toISOString(),action_url:"#/capas/c1"},
    {id:"n3",category:"Evidence",severity:"Warning",title:"18 طلب دليل متأخر",message:"راجع قائمة Evidence Inbox.",status:"Unread",created_at:new Date().toISOString(),action_url:"#/evidence"}
  ],
  findings:[
    {id:"f1",me_id:"MM.5.3",severity:"P0",status:"CAPAOpen",problem_statement:"لا توجد أدلة ممثلة على Independent Double Check في جميع المواقع والورديات.",owner_role_code:"MedicationSafety",due_date:"2026-08-02"},
    {id:"f2",me_id:"MM.41.8",severity:"P0",status:"Open",problem_statement:"RCA للحادثة المهمة لم يكتمل ولم يثبت اختبار الفعالية.",owner_role_code:"AccreditationLead",due_date:"2026-08-03"},
    {id:"f3",me_id:"MM.12.7",severity:"P1",status:"VerificationPending",problem_statement:"لا توجد حالة موثقة لإدارة انحراف حراري واتخاذ قرار صلاحية.",owner_role_code:"PharmacyDirector",due_date:"2026-08-05"},
    {id:"f4",me_id:"MM.25.2",severity:"P1",status:"Acknowledged",problem_statement:"Pre-dispensing pharmacist review gate غير مثبت على جميع أنواع الأوامر.",owner_role_code:"MEOwner",due_date:"2026-08-07"}
  ],
  evidence:[
    {id:"e1",me_id:"MM.20.3",tool:"OMR",collector:"الصيدلي السريري",status:"Requested",due:"2026-07-30",age:9},
    {id:"e2",me_id:"MM.31.7",tool:"O/I",collector:"مشرف الصرف",status:"Submitted",due:"2026-08-09",age:2},
    {id:"e3",me_id:"MM.39.4",tool:"OMR",collector:"الصيدلة السريرية",status:"UnderReview",due:"2026-08-06",age:5},
    {id:"e4",me_id:"MM.5.3",tool:"O/I",collector:"سلامة الدواء",status:"Returned",due:"2026-08-01",age:12}
  ],
  documents:[
    {code:"3-4",title:"High-Alert Medications Policy",status:"Effective",version:"2.1",review:"2026-11-30"},
    {code:"3-7",title:"Look-Alike / Sound-Alike Policy",status:"Review",version:"1.4",review:"2026-08-15"},
    {code:"5-13",title:"Verbal & Telephone Order Policy",status:"Effective",version:"3.0",review:"2027-01-12"},
    {code:"6-1",title:"Aseptic Technique for IV Medications",status:"Draft",version:"0.9",review:"—"},
    {code:"7-4",title:"Medication Errors",status:"Approved",version:"2.0",review:"2026-12-20"}
  ]
,
  // Deployment acceptance has no demo dataset by design (Sprint 23.9). It used
  // to live here as a hand-written list of gate verdicts and evidence strings
  // that the screen rendered as though they were measurements, and that no
  // live configuration change could ever move. The screen now reads
  // GET /deployment/acceptance-summary and shows NotAssessed when nothing has
  // been measured. Do not reintroduce a demo fallback here: a gate nobody
  // measured must say so, and tests assert these values are absent.
  operations:{operational_ready:false,slos:[{code:'API_AVAILABILITY',target:'>=99.5 %',value:99.8,status:'Pass'},{code:'API_P95_LATENCY',target:'<=750 ms',value:420,status:'Pass'},{code:'EVIDENCE_UPLOAD_SUCCESS',target:'>=99 %',value:97.4,status:'Breach'},{code:'BACKUP_FRESHNESS',target:'<=24 hours',value:null,status:'Pending'}],open_incidents:[{code:'SLO-EVIDENCE-UPLOAD',title:'Evidence upload success below target',severity:'P1',status:'Acknowledged',owner_role_code:'SystemAdmin'},{code:'CUT-IDENTITY-001',title:'OIDC user mapping requires retest',severity:'P1',status:'Open',owner_role_code:'SystemAdmin'}],cutover:{code:'TGH-CUT-001',status:'Draft',decision:'Pending',summary_json:{task_total:20,task_pass:8,critical_not_passed:['C09','C12','C13','C16','C17','C18','C19'],open_p0_p1_incidents:2,go_ready:false}},baseline:{code:'TGH-OPS-BASE-001',classification:'OperationalBaseline',status:'Draft',readiness_score:42,overall_status:'CriticalOpenActions',critical_open_actions:true}},
  pilot:{status:"ReadinessReview",gates_pass:12,gates_total:16,participants:8,p0_requests:48,uat_pass_rate:83.3,go_live_ready:false,blockers:["4 بوابات معلقة","سيناريو UAT حرج لم ينجح"],gates:[{code:"DATABASE_READY",status:"Pass",evidence:"runtime-smoke"},{code:"OIDC_CONFIGURED",status:"Pass",evidence:"claim-map"},{code:"BACKUP_RESTORE_TESTED",status:"Pending",evidence:""},{code:"UAT_CRITICAL_PASS",status:"Fail",evidence:"UAT-10 blocked"},{code:"SECURITY_ACCEPTANCE",status:"Pending",evidence:""}]},
  assurance:{programs:1,controls:48,overdue_controls:3,latest_cycle:{code:'TGH-ASSURE-2026-Q3',period_label:'2026-Q3',status:'Open',task_pass:29,task_fail:2,task_pending:17},data_quality:{issue_total:6,quality_pass:false,by_severity:{P0:1,P1:3,P2:2}},rollout_waves:[{code:'NBC-WAVE-01',name:'Northern Border first expansion wave',status:'InProgress',site_total:3,site_ready:1,site_blocked:2}]}
,
  intelligence:{average_risk:46.8,bands:{Critical:31,High:72,Moderate:104,Low:59},policy_status:'Effective',portfolio_sites:1,recommendations:[{me_id:'MM.41.8',title:'Human review recommended for RCA effectiveness',confidence:.91,status:'NeedsHumanReview'},{me_id:'MM.5.3',title:'Verify HAM double-check coverage across shifts',confidence:.88,status:'NeedsHumanReview'},{me_id:'MM.12.7',title:'Validate cold-chain backup and excursion response',confidence:.79,status:'HumanApprovedForPlanning'}]},
  action_planning:{pending_conversions:1,review_items:[{me_id:'MM.41.8',title:'RCA effectiveness review',decision:'AdoptForPlanning'},{me_id:'MM.5.3',title:'HAM double-check coverage',decision:'Defer'}],plans:[{code:'ACT-001',me_id:'MM.41.8',title:'Verify RCA effectiveness and governance',owner_role_code:'MedicationSafety',status:'InProgress',tasks_total:4,tasks_complete:2,linked_finding:true,linked_capa:false},{code:'ACT-002',me_id:'MM.12.7',title:'Cold-chain excursion verification',owner_role_code:'MEOwner',status:'Submitted',tasks_total:3,tasks_complete:0,linked_finding:false,linked_capa:false}]},
  committee_governance:{active_committees:1,session_status:'Blocked',unresolved_conflicts:1,members:[{code:'M-ACC',role:'AccreditationLead',authority_verified:true,training_verified:true},{code:'M-MED',role:'MedicationSafety',authority_verified:true,training_verified:true},{code:'M-AUD',role:'ReadOnlyAuditor',authority_verified:true,training_verified:true}],sessions:[{code:'TGH-IRC-2026-01',status:'Blocked',attended_voting_members:3,quorum_required:3,unresolved_conflicts:1,decision_count:0}],latest_metrics:{median_decision_hours:18.4,p90_decision_hours:29.1,median_plan_days:3.2,sla_breach_count:1,average_quality_score:86.0}},
  institutional_pilot:{run_mode:'Synthetic',status:'Draft',verified_identities:3,completed_sessions:1,adoption_events:12,feedback_count:4,average_feedback:4.25,published_reports:0,sessions:[{code:'TGH-PILOT-SESSION-001',status:'Completed',decision_count:1,quality_review_count:1,evidence_reference:'SYNTHETIC-MINUTES'}],metrics:[{code:'DECISION-TIME',name:'Median decision time',current_value:18,target_value:24,unit:'hours',status:'TargetMet',source_reference:'SYNTHETIC-METRIC'}]},
  governance:{security_controls:{total:12,pass:8,fail:1,pending:3},latest_release:{version:'1.3.0',status:'Draft',artifact_count:8,release_sha:'demo-sha',ready:false,missing:['SEC-SCAN-001']},active_legal_holds:1,retention_policies:2,audit_export_status:'Verified',sbom_status:'Attached',signature_status:'Partial',scan_status:'EvidenceRequired'}
};
