from database import Database

SPACE_QUIZ = {
    "title": "🚀 Космический квиз",
    "description": (
        "Семь вопросов о планетах, звёздах и первых полётах. "
        "Есть вопросы с вариантами, а есть такие, где ответ нужно <b>написать самому</b>.\n\n"
        "<i>После каждого ответа — короткий факт, так что в любом случае узнаешь что-то новое.</i>"
    ),
    "image": "asset:space.png",
    "questions": [
        {
            "kind": "choice",
            "text": "🪐 Какая планета Солнечной системы знаменита своими <b>кольцами</b>?",
            "image": "asset:planet.png",
            "options": ["Марс", "Сатурн", "Венера", "Меркурий"],
            "correct": 1,
            "explanation": (
                "Кольца есть у всех планет-гигантов, но только у Сатурна они такие яркие. "
                "Они состоят из кусочков льда и камня — от пылинок до глыб размером с дом."
            ),
        },
        {
            "kind": "choice",
            "text": "Сколько планет в Солнечной системе?",
            "options": ["7", "8", "9", "10"],
            "correct": 1,
            "explanation": "В 2006 году Плутон перевели в карликовые планеты — с тех пор их восемь.",
        },
        {
            "kind": "text",
            "text": "👨‍🚀 Назови фамилию первого человека, который полетел в космос.",
            "answers": ["Гагарин", "Юрий Гагарин", "Юрий Алексеевич Гагарин", "Gagarin"],
            "explanation": "12 апреля 1961 года, корабль «Восток-1». Весь полёт занял 108 минут.",
        },
        {
            "kind": "choice",
            "text": "🌗 Примерно за сколько дней Луна проходит полный цикл фаз — от новолуния до новолуния?",
            "image": "asset:moon.png",
            "options": ["7 дней", "14 дней", "29,5 дня", "365 дней"],
            "correct": 2,
            "explanation": "Это синодический месяц — около 29,5 суток. Отсюда, кстати, и привычная длина календарного месяца.",
        },
        {
            "kind": "choice",
            "text": "🔥 Какая планета самая горячая?",
            "options": ["Меркурий — она ближе всех к Солнцу", "Венера", "Марс", "Юпитер"],
            "correct": 1,
            "explanation": (
                "Венера горячее Меркурия: плотная атмосфера из углекислого газа держит тепло, "
                "как парник. На поверхности около +465 °C."
            ),
        },
        {
            "kind": "text",
            "text": "☀️ Какая звезда находится ближе всего к Земле?",
            "answers": ["Солнце", "The Sun", "Sun"],
            "explanation": (
                "Солнце! Следующая по близости — Проксима Центавра, до неё около 4,2 светового года."
            ),
        },
        {
            "kind": "choice",
            "text": "💡 Сколько примерно летит свет от Солнца до Земли?",
            "options": ["8 секунд", "8 минут", "8 часов", "8 дней"],
            "correct": 1,
            "explanation": "Около 8 минут 20 секунд. Так что Солнце мы всегда видим таким, каким оно было 8 минут назад.",
        },
    ],
}

SURVEY = {
    "title": "💬 Короткий опрос",
    "description": (
        "Три вопроса без правильных ответов — нам просто интересно твоё мнение. "
        "Займёт меньше минуты 🙏"
    ),
    "image": "asset:survey.png",
    "questions": [
        {
            "kind": "choice",
            "text": "Как часто ты проходишь квизы?",
            "options": ["Почти каждый день", "Иногда, под настроение", "Сегодня впервые"],
        },
        {
            "kind": "choice",
            "text": "Какую тему хочется следующей?",
            "options": ["🏛 История", "🎬 Кино и сериалы", "🔬 Наука", "🌍 География"],
        },
        {
            "kind": "text",
            "text": "Что бы ты добавил в бота? Любая идея подойдёт ✨",
        },
    ],
}


async def seed_demo(db: Database) -> bool:
    if await db.get_setting("seeded"):
        return False

    await db.set_setting("welcome_image", "asset:welcome.png")
    for pack in (SPACE_QUIZ, SURVEY):
        quiz_id = await db.create_quiz(pack["title"], pack["description"], pack["image"], published=True)
        for question in pack["questions"]:
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

    await db.set_setting("seeded", "1")
    return True
