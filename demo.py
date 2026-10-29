from database import Database

CONTENT_VERSION = "quiz-v3"
OLD_DEMO_TITLES = ("🚀 Космический квиз", "💬 Короткий опрос", "📐 Школьная математика", "📝 Квиз")

STARTER_QUIZ = {
    "title": "📝 Квиз",
    "description": (
        "15 вопросов.\n\n"
        "В одних нужно выбрать вариант, в других — <b>написать ответ сообщением</b>. "
        "<i>Не торопись: черновик пригодится, калькулятор — нет.</i>"
    ),
    "image": "asset:cover.png",
    "questions": [
        {
            "kind": "text",
            "image": "asset:q01.png",
            "text": "Сколько будет <b>17 × 23</b>?",
            "answers": ["391"],
            "explanation": "17 × 23 = (20 − 3)(20 + 3) = 400 − 9 = 391.",
        },
        {
            "kind": "choice",
            "image": "asset:q02.png",
            "text": "Найди корни уравнения <b>x² − 5x + 6 = 0</b>.",
            "options": ["2 и 3", "−2 и −3", "1 и 6", "−1 и 6"],
            "correct": 0,
            "explanation": "По теореме Виета сумма корней равна 5, а произведение 6. Это 2 и 3.",
        },
        {
            "kind": "text",
            "image": "asset:q03.png",
            "text": "Чему равна сумма внутренних углов выпуклого <b>шестиугольника</b>? Ответ в градусах.",
            "answers": ["720", "720°", "720 градусов"],
            "explanation": "Сумма углов n-угольника равна (n − 2) · 180°. Для шестиугольника: 4 · 180° = 720°.",
        },
        {
            "kind": "choice",
            "image": "asset:q04.png",
            "text": "Цену товара сначала повысили на 20%, а потом снизили на 20%. Как изменилась цена по сравнению с исходной?",
            "options": ["Не изменилась", "Снизилась на 4%", "Выросла на 4%", "Снизилась на 2%"],
            "correct": 1,
            "explanation": "1,2 · 0,8 = 0,96 — цена стала на 4% меньше исходной.",
        },
        {
            "kind": "text",
            "image": "asset:q05.png",
            "text": "Вычисли <b>log₂ 64</b>.",
            "answers": ["6"],
            "explanation": "2⁶ = 64, значит log₂ 64 = 6.",
        },
        {
            "kind": "choice",
            "image": "asset:q06.png",
            "text": "Найди наибольший общий делитель чисел <b>84</b> и <b>126</b>.",
            "options": ["14", "21", "42", "63"],
            "correct": 2,
            "explanation": "84 = 2² · 3 · 7, 126 = 2 · 3² · 7. Общие множители: 2 · 3 · 7 = 42.",
        },
        {
            "kind": "text",
            "image": "asset:q07.png",
            "text": "Чему равна сумма всех натуральных чисел от <b>1</b> до <b>100</b>?",
            "answers": ["5050"],
            "explanation": "Составим пары 1 + 100, 2 + 99, … — получится 50 пар по 101. Итого 5050.",
        },
        {
            "kind": "choice",
            "image": "asset:q08.png",
            "text": "Чему равно <b>sin 30° + cos 60°</b>?",
            "options": ["1/2", "1", "√3/2", "√3"],
            "correct": 1,
            "explanation": "sin 30° = 1/2 и cos 60° = 1/2, в сумме 1.",
        },
        {
            "kind": "text",
            "image": "asset:q09.png",
            "text": "Площадь круга радиусом <b>3</b> равна <b>k · π</b>. Найди k.",
            "answers": ["9", "k = 9", "к = 9"],
            "explanation": "S = πr² = π · 3² = 9π, значит k = 9.",
        },
        {
            "kind": "choice",
            "image": "asset:q10.png",
            "text": "Бросают два игральных кубика. Какова вероятность, что в сумме выпадет <b>7</b>?",
            "options": ["1/12", "1/9", "1/6", "7/36"],
            "correct": 2,
            "explanation": "Всего 36 исходов, подходят 6: (1,6), (2,5), (3,4), (4,3), (5,2), (6,1). 6/36 = 1/6.",
        },
        {
            "kind": "text",
            "image": "asset:q11.png",
            "text": "Дана арифметическая прогрессия <b>3, 7, 11, …</b> Найди её <b>20-й</b> член.",
            "answers": ["79"],
            "explanation": "aₙ = a₁ + (n − 1)d = 3 + 19 · 4 = 79.",
        },
        {
            "kind": "choice",
            "image": "asset:q12.png",
            "text": "Вычисли <b>(2³)² · 2⁻⁴</b>.",
            "options": ["2", "4", "8", "16"],
            "correct": 1,
            "explanation": "(2³)² = 2⁶, а 2⁶ · 2⁻⁴ = 2² = 4.",
        },
        {
            "kind": "text",
            "image": "asset:q13.png",
            "text": "Реши систему: <b>x + y = 10</b>, <b>x − y = 4</b>. Чему равно <b>x · y</b>?",
            "answers": ["21"],
            "explanation": "Сложим уравнения: 2x = 14, x = 7. Тогда y = 3, а x · y = 21.",
        },
        {
            "kind": "choice",
            "image": "asset:q14.png",
            "text": "Сторона квадрата равна <b>5</b>. Чему равна его диагональ?",
            "options": ["5", "5√2", "10", "25"],
            "correct": 1,
            "explanation": "По теореме Пифагора: d² = 5² + 5² = 50, d = √50 = 5√2.",
        },
        {
            "kind": "text",
            "image": "asset:q15.png",
            "text": "Сколько всего диагоналей у выпуклого <b>восьмиугольника</b>?",
            "answers": ["20"],
            "explanation": "Формула n(n − 3) / 2: 8 · 5 / 2 = 20.",
        },
    ],
}


async def seed_demo(db: Database) -> bool:
    if await db.get_setting("content") == CONTENT_VERSION:
        return False

    for quiz in await db.quizzes():
        if quiz.title in OLD_DEMO_TITLES:
            await db.delete_quiz(quiz.id)

    if not await db.get_setting("welcome_image"):
        await db.set_setting("welcome_image", "asset:welcome.png")

    quiz_id = await db.create_quiz(
        STARTER_QUIZ["title"], STARTER_QUIZ["description"], STARTER_QUIZ["image"], published=True
    )
    for question in STARTER_QUIZ["questions"]:
        await db.add_question(
            quiz_id,
            kind=question["kind"],
            text=question["text"],
            image=question.get("image"),
            options=question.get("options"),
            correct=question.get("correct"),
            answers=question.get("answers"),
            explanation=question.get("explanation", ""),
        )

    await db.set_setting("content", CONTENT_VERSION)
    return True
