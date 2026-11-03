---
collection: "Saudi-Principles"
reader_guide: true
volumes:
- "Admin-principles-1443-v6"
---

<div dir="rtl">

# دليل القارئ لمستودع مبادئ المحكمة الإدارية العليا

هذا المستودع مجموعة ملفات Markdown مولّدة آليًا من ملفات PDF لمجموعات المبادئ التي قررتها المحكمة الإدارية العليا الصادرة عن ديوان المظالم. كل مبدأ في ملف مستقل، وكل مجلد في مجلد مستقل باسمه الإنجليزي.

## قواعد المعرّفات

- معرّف المجلد: `<Name>-principles-<YYYY>-v<N>` (مثل `Admin-principles-1443-v6`)؛ وهو اسم مجلد الملفات أيضًا.

- معرّف المبدأ: `<volume_id>:p<NNN>`؛ الرمز `p` يسبق رقم المبدأ كما طُبع في المجلد مكمَّلًا بالأصفار إلى ثلاث خانات على الأقل؛ اسم الملف هو الجزء بعد النقطتين مع `.md` (مثل `p383.md`). ولا يُمنح الرقم الواحد أكثر من معرّف؛ فإذا ورد في الفهرس تحت أكثر من موضوع فكل ورود «موضع» (facet) داخل الملف نفسه.

- معرّفات الحروف والموضوعات في فهرس المجلد (`<volume_id>:L-<letter>`، `…-<NN>`) للتصفح فقط.

- معرّف المرجع القضائي: `<volume_id>:r-<prefix>-<number>-<year>` داخلي، يجمع المبادئ التي تذكر المرجع نفسه.

## تخطيط المجلدات والملفات

- `README.md` (هذا الدليل) و`index.md` (سجل المجلدات) في جذر المستودع.

- لكل مجلد: `index.md` (فهرس المجلد المولَّد)، و`volume-details.md` (بيانات المجلد كما وردت)، و`Indexes/summary-index.md` و`Indexes/detailed-index.md` (جدولا الفهرس كما وردا صفحةً صفحة)، و`Principles/pNNN.md` (ملف لكل رقم مبدأ).

## مفاتيح الواجهة الأمامية (YAML) وقيمها

- `volume_id`، `collection_name_ar`، `collection_name_en`، `year_hijri`، `volume_number`: هوية المجلد.

- `principle_id`، `principle_number`، `principle_title_ar` (عنوان الموضع الأول)، `principle_title_en` (`Principle N`)، `title_basis` ∈ {`bullet_title`, `subtopic_line`, `none`}.

- `citation_ar`، `citation_en`، `citation_full_ar`، `citation_full_en`: صيغ الاستشهاد المولَّدة من بيانات المجلد.

- `text_basis` ∈ {`index_wording`, `principle_file`, `index_and_body_identical`}: صيغة الفهرس هي بيان المحرر للمبدأ، ونص الملف هو مستخرج الحكم؛ والقسم الافتراضي للقراءة هو «نص المبدأ» عند وجود الملف وإلا «صيغة المبدأ في الفهرس». `body_supplied` يكون `false` عندما لا يكون ملف المبدأ مزوّدًا؛ فلا يحمل الملف حينئذ إلا صيغة الفهرس.

- `hierarchy_ar`: قائمة من {`level` ∈ {letter, topic, subtopic}, `label_ar`, `title_ar`} للموضع الأول؛ `index_facets`: كل مواضع الرقم في الفهرس بترتيب المصدر، ولكل موضع `entry_kind` ∈ {entry, sibling, continuation, see_also} وعنوانه وتسلسله وصفحته ومراجعه ومواقعه.

- `page_labels`: أرقام الصفحات كما طُبعت في عمود «ص»؛ أما `page[P]` في المواقع فهو رقم الصفحة الفعلي في ملف PDF.

- `ruling_references`: المراجع كما وردت بين قوسين (`ref_ar`) مع مكوناتها الثلاثة (`prefix_ar`, `number`, `year_hijri`)؛ `meaning_basis: not_asserted` يعني أن المستودع لا يفسر معنى المكونات ما لم يحدده الإعداد.

- `related_principles`: `relation` ∈ {`shared_index_entry`, `sibling_under_title`, `see_also`, `referenced_by_see_also`, `same_ruling_reference`}؛ روابط «راجع» هي إحالات الفهرس نفسه. `target_supplied: false` مع `target_citation_ar` عند تعذر العثور على المحال إليه في الفهرس المزوّد.

- `see_also_ar`: نص الإحالة كما ورد. `source_anomalies: true` عند تسجيل ملاحظة على نص المصدر لهذا المبدأ. `open_issues`: بنود المراجعة غير المحلولة.

- `sources`: `file`، `kind` ∈ {index, principle}، `heading_locations`، `text_locations`، `reference_locations`، `number_locations`، `note_locations`، `extraction` ∈ {`text_layer_repaired`, `ocr`}: الأولى تعني أن النص قُرئ من طبقة النص بعد إصلاح المحارف المعيبة وفق إعداد المجلد، والثانية أن قرارًا نشر قراءة التعرف الضوئي.

- `index_file` و`details_file`: مساران نسبيان إلى فهرس المجلد وبيانات المجلد. داخل `index_facets`: `shared_with` (معرّفات الأرقام المشاركة في مدخل واحد) و`pairing_basis` ∈ {`positional`, `confirmed_by_body`} و`heading_location` و`text_location` (مواقع المصدر). داخل `related_principles`: `principle_id` و`title_ar` (صيغة الاستشهاد المختصرة للهدف) و`path` (المسار النسبي لملف الهدف)، أو `target_held: true` عندما يكون الهدف محجوزًا للمراجعة بلا ملف.

- في فهرس المجلد: `principle_count` (الملفات المنشورة) و`principles_with_body` و`principles_held` (أرقام محجوزة للمراجعة بلا ملف) و`letters` (الشجرة الهجائية بمعرّفاتها). في بيانات المجلد: `cataloging` (`deposit_number`, `isbn`, `extent_ar`, `reading_basis` كما طُبعت) و`extraction_summary` (الخطوط وحالة طبقة النص وعدد الإصلاحات وإحصاء المحارف والضمّات) و`year_gregorian_computed` (نطاق السنة الهجرية ميلاديًا، محسوب).

## مواقع المصدر

- `page[P]` صفحة فعلية (1-based)؛ `:r<i>:c<j>` صف وعمود الجدول (العمود 0 هو الأيمن: «المبدأ»، ثم «الرقم»، ثم «ص»)؛ `:L<k>` سطر داخل الخلية (0-based) قبل ضم الأسطر الملتفة.

## ملاحظات

- الأرقام في الملفات بالأرقام الغربية، والنص بالترتيب المنطقي وبصيغة NFC.

- غلاف الكتاب وصفحة البسملة والصفحات الفاصلة والترويسة والتذييل مستبعدة بقرار المستخدم؛ وصفحة الفهرسة محفوظة مرة واحدة في `volume-details.md`.

- لا يحوّل المستودع تواريخ المبادئ؛ والسنة الهجرية للمجلد تُذكر كما وردت، ويُذكر في `volume-details.md` نطاقها الميلادي محسوبًا.

## المجلدات

- [مجموعة المبادئ التي قررتها المحكمة الإدارية العليا لعام 1443هـ — المجلد السادس](Admin-principles-1443-v6/index.md)

</div>
