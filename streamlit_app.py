import io
import pypdf
import PIL.Image
import pypdfium2 as pdfium
import streamlit as st
import google.generativeai as genai

st.set_page_config(
    page_title="مُختصِر - مساعد الامتحانات الذكي",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <meta name="theme-color" content="#0f172a">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <style>
        .main .block-container {
            direction: rtl;
            text-align: right;
        }
        div[data-testid="stSidebar"] {
            direction: rtl;
            text-align: right;
        }
        button, input, textarea, select {
            direction: rtl;
            text-align: right;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_mode" not in st.session_state:
    st.session_state.last_mode = ""


def extract_text_from_pdf(file_bytes: bytes, max_pages: int = 1000) -> tuple[str, int]:
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    total_pages = len(reader.pages)
    pages_to_read = min(total_pages, max_pages)
    extracted_parts = []
    for idx in range(pages_to_read):
        page_text = reader.pages[idx].extract_text() or ""
        page_text = page_text.strip()
        if page_text:
            extracted_parts.append(f"--- صفحة {idx + 1} ---\n{page_text}")
    return "\n\n".join(extracted_parts), total_pages


def render_scanned_pages_to_images(
    file_bytes: bytes, max_pages: int = 1000, scale: float = 1.5
) -> tuple[list[PIL.Image.Image], int]:
    pdf_doc = pdfium.PdfDocument(file_bytes)
    total_pages = len(pdf_doc)
    pages_to_render = min(total_pages, max_pages)
    images = []
    for idx in range(pages_to_render):
        page = pdf_doc[idx]
        bitmap = page.render(scale=scale)
        pil_img = bitmap.to_pil()
        images.append(pil_img)
    return images, total_pages


def build_prompt(mode: str, custom_notes: str = "") -> str:
    extra = f"\nملاحظات إضافية من الطالب: {custom_notes.strip()}" if custom_notes.strip() else ""
    if mode == "الزيتونة (ملخص شامل ومركّز)":
        return (
            "أنت مساعد أكاديمي ذكي متخصص في مراجعة المحاضرات والكتب الجامعية بسرعة ودقة. "
            "قدّم ملخصاً شاملاً ومنظماً وواضحاً باللغة العربية الفصحى المبسطة (مع الاحتفاظ بالمصطلحات العلمية بالإنجليزية إن وُجدت)، "
            "واستخرج أهم النقاط والمفاهيم والتعريفات والمقارنات الأساسية للمذاكرة قبل الامتحان."
            f"{extra}"
        )
    if mode == "رادار الامتحان (توقعات ونقاط مهمة)":
        return (
            "أنت خبير امتحانات جامعية. حلّل المحتوى المرفق وحدد بدقة:"
            " 1) أكثر الموضوعات والفقرات ترشيحاً لأسئلة الامتحان ولماذا."
            " 2) المصطلحات والتعاريف والاختلافات التي يكثر فيها الخداع أو الأسئلة."
            " 3) خطة مراجعة سريعة لأهم النقاط."
            f"{extra}"
        )
    return (
        "أنت واضع اختبارات جامعية محترف. أنشئ بنك أسئلة متنوع وشامل يعتمد على المحتوى المرفق فقط، "
        "ويشمل: أسئلة اختيار من متعدد (MCQ) مع توضيح الإجابة الصحيحة، وأسئلة صح وخطأ مع التصحيح، "
        "وأسئلة مقالية قصيرة مع نموذج إجابة مختصر ودقيق."
        f"{extra}"
    )


def run_gemini_analysis(
    api_key: str,
    model_name: str,
    mode: str,
    extracted_text: str,
    scanned_images: list[PIL.Image.Image],
    custom_notes: str,
) -> str:
    genai.configure(api_key=api_key.strip())
    model = genai.GenerativeModel(model_name)
    prompt = build_prompt(mode, custom_notes)

    contents: list = [prompt]
    if extracted_text.strip():
        contents.append(f"النص المستخرج من الملف:\n\n{extracted_text}")
    if scanned_images:
        contents.extend(scanned_images)

    response = model.generate_content(contents)
    return response.text or "لم يتم إرجاع نص من النموذج."


st.title("🎯 مُختصِر - مساعد الامتحانات الذكي")
st.caption("ارفع ملف PDF (نصي أو Scan حتى 1000 صفحة) أو صوراً للمحاضرات، واختر أداة المذاكرة المناسبة.")

with st.sidebar:
    st.header("⚙️ الإعدادات")
    api_key = st.text_input("مفتاح Gemini API Key", type="password", placeholder="AIza...")
    model_name = st.selectbox(
        "اختر النموذج",
        options=["gemini-1.5-flash", "gemini-1.5-pro"],
        index=0,
    )
    max_pages = st.slider("الحد الأقصى لعدد الصفحات", min_value=1, max_value=1000, value=100)
    custom_notes = st.text_area("تعليمات إضافية (اختياري)", placeholder="مثال: ركّز على الفصل الأول والثاني...")

uploaded_files = st.file_uploader(
    "ارفع ملفات PDF أو صور المحاضرات",
    type=["pdf", "png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)

extracted_text_chunks = []
scanned_images_all = []
direct_images = []
total_pdf_pages_seen = 0

if uploaded_files:
    for up_file in uploaded_files:
        raw_bytes = up_file.getvalue()
        file_name_lower = up_file.name.lower()

        if file_name_lower.endswith(".pdf"):
            text_out, pdf_pages = extract_text_from_pdf(raw_bytes, max_pages=max_pages)
            total_pdf_pages_seen += min(pdf_pages, max_pages)

            if text_out.strip():
                extracted_text_chunks.append(f"=== ملف: {up_file.name} ===\n{text_out}")
            else:
                st.info(f"الملف **{up_file.name}** يبدو ممسوحاً ضوئياً (Scan) — جاري تحويل الصفحات إلى صور...")
                imgs, _ = render_scanned_pages_to_images(raw_bytes, max_pages=max_pages, scale=1.5)
                scanned_images_all.extend(imgs)
        else:
            img = PIL.Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            direct_images.append(img)

    st.success(
        f"تم تحميل {len(uploaded_files)} ملف | صفحات PDF المعالجة: {total_pdf_pages_seen} | "
        f"صفحات Scan محوّلة: {len(scanned_images_all)} | صور مباشرة: {len(direct_images)}"
    )

combined_text = "\n\n".join(extracted_text_chunks)
all_images = scanned_images_all + direct_images

c1, c2, c3 = st.columns(3)

with c1:
    if st.button("🫒 الزيتونة", use_container_width=True):
        try:
            with st.spinner("جاري تجهيز الزيتونة..."):
                if not api_key:
                    st.warning("من فضلك أدخل مفتاح Gemini API Key من القائمة الجانبية أولاً.")
                elif not combined_text.strip() and not all_images:
                    st.warning("من فضلك ارفع ملف PDF أو صوراً أولاً.")
                else:
                    mode_label = "الزيتونة (ملخص شامل ومركّز)"
                    result = run_gemini_analysis(
                        api_key=api_key,
                        model_name=model_name,
                        mode=mode_label,
                        extracted_text=combined_text,
                        scanned_images=all_images,
                        custom_notes=custom_notes,
                    )
                    st.session_state.last_result = result
                    st.session_state.last_mode = mode_label
        except Exception as e:
            st.error(f"❌ خطأ: {e}")

with c2:
    if st.button("🔥 رادار الامتحان", use_container_width=True):
        try:
            with st.spinner("جاري تشغيل رادار الامتحان..."):
                if not api_key:
                    st.warning("من فضلك أدخل مفتاح Gemini API Key من القائمة الجانبية أولاً.")
                elif not combined_text.strip() and not all_images:
                    st.warning("من فضلك ارفع ملف PDF أو صوراً أولاً.")
                else:
                    mode_label = "رادار الامتحان (توقعات ونقاط مهمة)"
                    result = run_gemini_analysis(
                        api_key=api_key,
                        model_name=model_name,
                        mode=mode_label,
                        extracted_text=combined_text,
                        scanned_images=all_images,
                        custom_notes=custom_notes,
                    )
                    st.session_state.last_result = result
                    st.session_state.last_mode = mode_label
        except Exception as e:
            st.error(f"❌ خطأ: {e}")

with c3:
    if st.button("📝 بنك أسئلة", use_container_width=True):
        try:
            with st.spinner("جاري إنشاء بنك الأسئلة..."):
                if not api_key:
                    st.warning("من فضلك أدخل مفتاح Gemini API Key من القائمة الجانبية أولاً.")
                elif not combined_text.strip() and not all_images:
                    st.warning("من فضلك ارفع ملف PDF أو صوراً أولاً.")
                else:
                    mode_label = "بنك أسئلة (اختياري، صح وخطأ، مقالي)"
                    result = run_gemini_analysis(
                        api_key=api_key,
                        model_name=model_name,
                        mode=mode_label,
                        extracted_text=combined_text,
                        scanned_images=all_images,
                        custom_notes=custom_notes,
                    )
                    st.session_state.last_result = result
                    st.session_state.last_mode = mode_label
        except Exception as e:
            st.error(f"❌ خطأ: {e}")

if st.session_state.last_result:
    st.markdown("---")
    st.markdown(f"### {st.session_state.last_mode}")
    st.markdown(st.session_state.last_result)

    st.download_button(
        label="⬇️ تحميل النتيجة كملف نصي (TXT)",
        data=st.session_state.last_result,
        file_name="mokhtaser_result.txt",
        mime="text/plain",
      )
