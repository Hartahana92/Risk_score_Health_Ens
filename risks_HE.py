import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="MetaboScores", layout="wide")
st.title("📊 Расчёт финального скора по метаболическим осям (встроенные оси)")

st.markdown("""
Загрузите Excel c рисками пациентов (столбец **«Код»** + столбцы осей).  
Веса осей встроены в приложение и настраиваются слайдерами в боковой панели.
""")

# ------------------ ВСТРОЕННЫЕ ОСИ И ДЕФОЛТНЫЕ ВЕСА ------------------
AXES_DEFAULTS = {
    "Воспаление и иммунная активация": 0.10,
    "Здоровье митохондрий": 0.10,
    "Метаболическая адаптация и стрессоустойчивость": 0.10,
    "Метаболическая детоксикация": 0.10,
    "Оценка пролиферативных процессов": 0.0,
    "Состояние дыхательной системы": 0.10,
    "Состояние иммунного метаболического баланса": 0.10,
    "Состояние сердечно-сосудистой системы": 0.10,
    "Состояние функции печени": 0.01,
    "Статус микробиоты": 0.01,
    "Цикл Кребса и баланс аминокислот": 0.01,
}

# --------- ФАЙЛ С РИСКАМИ ---------
risks_file = st.file_uploader("Загрузите файл с рисками пациентов (Excel, .xlsx)", type=["xlsx"])

# --------- SIDEBAR: НАСТРОЙКА ВЕСОВ ---------
st.sidebar.header("⚙️ Настройка весов осей")
st.sidebar.caption("Диапазон каждого веса: 0.01 – 0.50")

MIN_W, MAX_W, STEP_W = 0.01, 0.50, 0.01

# Новый параметр — степень экспоненты для value < 7
st.sidebar.markdown("---")
alpha = st.sidebar.number_input(
    "Показатель степени при value < 7",
    min_value=1.0,
    max_value=3.0,
    value=1.7,
    step=0.1,
    format="%.1f",
    help="Используется в формуле (1 - (x ** α)) при value < 7"
)
st.sidebar.markdown("---")
# инициализация состояния
if "weights_state" not in st.session_state:
    st.session_state["weights_state"] = AXES_DEFAULTS.copy()

# слайдеры весов
for axis in AXES_DEFAULTS.keys():
    st.session_state["weights_state"][axis] = st.sidebar.slider(
        axis,
        min_value=float(MIN_W),
        max_value=float(MAX_W),
        value=float(st.session_state["weights_state"][axis]),
        step=float(STEP_W),
        key=f"slider_{axis}"
    )

weights_series = pd.Series(st.session_state["weights_state"], name="Weight")
weights_sum = float(weights_series.sum())
st.sidebar.metric("Σ Сумма весов", f"{weights_sum:.2f}")


# кнопка сброса
if st.sidebar.button("↩️ Сбросить к значениям по умолчанию"):
    for k, v in AXES_DEFAULTS.items():
        st.session_state["weights_state"][k] = v
        st.session_state[f"slider_{k}"] = v
    st.rerun()

# --------- ЧТЕНИЕ РИСКОВ И РАСЧЁТ ---------
def read_risks(file):
    # укажем движок явно на случай конфликтов
    return pd.read_excel(file, engine="openpyxl")

if risks_file is not None:
    try:
        df = read_risks(risks_file)
        if "Код" not in df.columns:
            st.error("В загруженном файле должен присутствовать столбец «Код».")
            st.stop()

        # какие столбцы считаем осями
        risk_groups = [c for c in df.columns if c not in ("Код", "Пациент")]

        # предупреждения о несоответствии
        missing_in_file = [ax for ax in AXES_DEFAULTS if ax not in df.columns]
        extra_in_file = [c for c in risk_groups if c not in AXES_DEFAULTS]
        if missing_in_file:
            st.warning("В файле отсутствуют следующие оси (будут пропущены в расчёте): " + ", ".join(missing_in_file))
        if extra_in_file:
            st.info("В файле есть дополнительные столбцы, не входящие во встроенный список осей (будут пропущены): " + ", ".join(extra_in_file))

        # используем только пересечение
        risk_groups = [r for r in risk_groups if r in AXES_DEFAULTS]

        # расчёт
        final_scores = []
        for i, code in enumerate(df["Код"].values):
            summ_score = 0.0
            for risk in risk_groups:
                value = pd.to_numeric(df.loc[i, risk], errors="coerce")
                if pd.isna(value):
                    continue
                w = float(weights_series.loc[risk])
                x = value / 10.0
                # та же логика порогов: <7 — экспонента 1.7; иначе линейно
                a = w * (1 - (x**alpha)) if value < 7 else w * (1 - x)

                summ_score += a
            final_score = round(min(5.0, 5.0 * summ_score), 1)
            final_scores.append(final_score)

        result_df = pd.DataFrame({
            "Пациент": df["Код"].values,
            "Финальный скор": final_scores
        })

        st.subheader("📈 Результаты")
        c1, c2 = st.columns(2)
        #with c1:
        #    st.metric("Σ Сумма весов (текущие)", f"{weights_sum:.2f}")
        #with c2:
        #    st.metric("Средний финальный скор", f"{np.mean(final_scores):.2f}")

        st.dataframe(result_df, use_container_width=True)

        # --------- ЭКСПОРТ ---------
        @st.cache_data
        def to_csv(df_out: pd.DataFrame) -> bytes:
            return df_out.to_csv(index=False).encode("utf-8")

        @st.cache_data
        def to_xlsx(df_out: pd.DataFrame, weights_out: pd.Series) -> bytes:
            bio = BytesIO()
            with pd.ExcelWriter(bio, engine="openpyxl") as writer:
                df_out.to_excel(writer, index=False, sheet_name="Результаты")
                wdf = weights_out.rename("Weight").to_frame()
                wdf.to_excel(writer, sheet_name="Веса (текущие)")
            return bio.getvalue()

        csv_bytes = to_csv(result_df)
        xlsx_bytes = to_xlsx(result_df, weights_series)

        d1, d2 = st.columns(2)
        #with d1:
        #    st.download_button("⬇️ Скачать результаты (CSV)", data=csv_bytes,
        #                       file_name="final_scores.csv", mime="text/csv")
        with d2:
            st.download_button("⬇️ Скачать результаты (Excel)", data=xlsx_bytes,
                               file_name="final_scores.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"Ошибка при обработке файла рисков: {e}")
else:
    st.info("Загрузите Excel с рисками пациентов, затем настройте веса в боковой панели.")
