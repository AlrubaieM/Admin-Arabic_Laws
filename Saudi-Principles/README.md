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

- معرّف المبدأ: `<volume_id>:p<NNN>`؛ الرمز `p` يسبق رقم المبدأ كما طُبع في المجلد مكمَّلًا بالأصفار إلى ثلاث خانات على الأقل؛ اسم الملف هو الجزء بعد النقطتين مع `.md` (مثل `p383.md`). ولا يُمنح الرقم الواحد أكثر من معرّف؛ فإذا ورد في الفهرس تحت أكثر من موضوع فكل ورود «موضع» (facet) داخل الملف نفسه. وإذا قرر المستخدم فصل رقم طُبع لمبدأين مختلفين (قرار `split`) نُشر الثاني بلاحقة `-dup2` (مثل `p101-dup2.md`).

- معرّفات الحروف والموضوعات في فهرس المجلد (`<volume_id>:L-<letter>`، `…-<NN>`، `…-<NN>-<NN>`) للتصفح فقط؛ الحرف مُحوَّل بجدول ثابت.

- معرّف المرجع القضائي: `<volume_id>:r-<prefix>-<number>-<year>` داخلي، يجمع المبادئ التي تذكر المرجع نفسه؛ ولا يُمنح لمرجع حرفُه خارج الجدول الثابت.

## تخطيط المجلدات والملفات

- `README.md` (هذا الدليل) و`index.md` (سجل المجلدات) في جذر المستودع.

- لكل مجلد: `index.md` (فهرس المجلد المولَّد)، و`volume-details.md` (بيانات المجلد كما وردت)، و`Indexes/summary-index.md` و`Indexes/detailed-index.md` (جدولا الفهرس كما وردا صفحةً صفحة؛ صف رأس الجدول الإجمالي مولَّد لأن المصدر لا يطبع رأسًا، وهو موسوم بذلك)، و`Principles/pNNN.md` (ملف لكل رقم مبدأ منشور).

- المبدأ «المحجوز للمراجعة» رقمٌ لم يُنشر له ملف لأن في سطره محرفًا لم يُحل أو لأن مدخله بلا صيغة؛ يذكره فهرس المجلد مع أرقام بنود المراجعة في `work/review/`، ويُنشر بعد الإصلاح أو القرار.

## مفاتيح الواجهة الأمامية (YAML) وقيمها

ملف المبدأ:

- `volume_id`، `collection_name_ar`، `collection_name_en`، `year_hijri`، `volume_number`: هوية المجلد.

- `principle_id`، `principle_number`، `principle_title_ar` (عنوان الموضع الأول)، `principle_title_en` (`Principle N`)، `title_basis` ∈ {`bullet_title`, `subtopic_line`, `none`}.

- `citation_ar`، `citation_en`، `citation_full_ar`، `citation_full_en`: صيغ الاستشهاد المولَّدة من بيانات المجلد؛ يُحذف من الصيغة الكاملة ما لم يرد في المصدر (عنوان أو صفحة أو مرجع) ويُسجَّل الحذف في `open_issues`.

- `text_basis` ∈ {`index_wording`, `principle_file`, `index_and_body_identical`}: صيغة الفهرس هي بيان المحرر للمبدأ، ونص الملف هو مستخرج الحكم؛ والقسم الافتراضي للقراءة هو «نص المبدأ» عند وجود الملف وإلا «صيغة المبدأ في الفهرس». `body_supplied` يكون `false` عندما لا يكون ملف المبدأ مزوّدًا؛ فلا يحمل الملف حينئذ إلا صيغة الفهرس.

- `index_file` و`details_file`: مساران نسبيان إلى فهرس المجلد وبيانات المجلد.

- `hierarchy_ar`: قائمة من {`level` ∈ {letter, topic, subtopic}, `label_ar`, `title_ar`} للموضع الأول.

- `page_labels`: أرقام الصفحات كما طُبعت في عمود «ص»؛ أما `page[P]` في المواقع فهو رقم الصفحة الفعلي في ملف PDF.

- `ruling_references`: المراجع كما وردت بين قوسين (`ref_ar`) مع مكوناتها الثلاثة (`prefix_ar`, `number`, `year_hijri`) و`ref_id` (عند وجود حرف المرجع في الجدول الثابت)؛ `meaning_basis` ∈ {`not_asserted`, `user_assigned`}: الأولى تعني أن المستودع لا يفسر معنى المكونات ما لم يحدده الإعداد.

- `related_principles`: `principle_id` و`title_ar` (صيغة الاستشهاد المختصرة للهدف) و`path` (المسار النسبي لملف الهدف) أو `target_held: true` عندما يكون الهدف محجوزًا للمراجعة بلا ملف؛ `relation` ∈ {`shared_index_entry`, `sibling_under_title`, `see_also`, `referenced_by_see_also`, `same_ruling_reference`}؛ روابط «راجع» هي إحالات الفهرس نفسه. `target_supplied: false` مع `target_citation_ar` عند تعذر العثور على المحال إليه في الفهرس المزوّد.

- `index_facets`: كل مواضع الرقم في الفهرس بترتيب المصدر، ولكل موضع `facet` و`entry_kind` ∈ {entry, sibling, continuation, see_also} و`title_ar` و`title_basis` و`hierarchy_ar` و`page_label` و`ruling_references` و`shared_with` (معرّفات الأرقام المشاركة في مدخل واحد) و`pairing_basis` ∈ {`positional`, `confirmed_by_body`} و`heading_location` و`text_location`.

- `see_also_ar`: نصوص الإحالة كما وردت. `status_from_source`: حالة يذكرها المصدر نفسه (لم تُلاحظ في العينة). `source_anomalies: true` عند تسجيل ملاحظة على نص المصدر لهذا المبدأ. `open_issues`: بنود المراجعة غير المحلولة ({`item_id`, `issue`}).

- `sources`: مدخل لكل ملف مصدر: `file`، `kind` ∈ {index, principle}، `heading_locations`، `text_locations`، `reference_locations`، `number_locations`، `note_locations`، `identical_wording: true` (ملف آخر يحمل الصيغة نفسها)، `extraction` ∈ {`text_layer_repaired`, `ocr`}: الأولى تعني أن النص قُرئ من طبقة النص بعد إصلاح المحارف المعيبة وفق إعداد المجلد، والثانية أن قرارًا نشر قراءة التعرف الضوئي.

فهرس المجلد (`index.md`): `principle_count` (الملفات المنشورة) و`principles_with_body` و`principles_held` (أرقام محجوزة بلا ملف) و`letters` (الشجرة الهجائية: `letter_id`, `letter_ar`, `topics` [`topic_id`, `title_ar`, `subtopics` [`subtopic_id`, `label_ar`, `title_ar`]]).

جدولا الفهرس (`Indexes/*.md`): `index_kind` ∈ {summary, detailed} و`physical_pages` و`printed_labels`.

بيانات المجلد (`volume-details.md`): `collection_name_en_basis` ∈ {official_supplied, user_assigned, descriptive} و`volume_ordinal_ar` و`publisher_ar` و`publisher_unit_ar` و`cataloging` (`deposit_number`, `isbn`, `extent_ar` كما طُبعت) و`source_origin` و`sources` (`file`, `kind`, `page_classes`, `extraction`) و`extraction_summary` (`fonts`, `text_layer` ∈ {defective, reliable}, `glyph_repairs_applied`, `ocr_confirmed_lines`, `ocr_disagreements` عند وجود سجل للتعرف الضوئي) و`year_gregorian_computed` (نطاق السنة الهجرية ميلاديًا بصيغة DD/MM/YYYY، محسوب) و`date_format` و`date_conversion_method`.

سجل المجلدات (`index.md` في الجذر): لكل مجلد `volume_id` و`collection_name_ar` و`collection_name_en` و`year_hijri` و`volume_number` و`folder` و`principle_count` و`principles_with_body` و`principles_held`.

## مواقع المصدر

- `page[P]` صفحة فعلية (1-based)؛ `:r<i>:c<j>` صف وعمود الجدول (العمود 0 هو الأيمن: «المبدأ»، ثم «الرقم»، ثم «ص»)؛ `:L<k>` سطر داخل الخلية (0-based) قبل ضم الأسطر الملتفة.

## ملاحظات

- الأرقام في الملفات بالأرقام الغربية، والنص بالترتيب المنطقي وبصيغة NFC. وتُقرأ الأرقام داخل المرجع القضائي من اليمين إلى اليسار عددًا عددًا كما طُبعت.

- غلاف الكتاب وصفحة البسملة والصفحات الفاصلة والترويسة والتذييل مستبعدة بقرار المستخدم؛ وصفحة الفهرسة محفوظة مرة واحدة في `volume-details.md`، وسطور الغلاف منقولة من صورته.

- لا يحوّل المستودع تواريخ المبادئ؛ والسنة الهجرية للمجلد تُذكر كما وردت، ويُذكر في `volume-details.md` نطاقها الميلادي محسوبًا.

## المجلدات

- [مجموعة المبادئ التي قررتها المحكمة الإدارية العليا لعام 1443هـ — المجلد السادس](Admin-principles-1443-v6/index.md)

</div>
