async def handle_booking(session, user_text, slot_manager, mss_client):
    if session.state == "ASK_SPECIALTY":
        # 1. Нашли врача по специальности
        doctor = find_doctor(mss_client, session.collected_data["specialty"])

        # 2. Нашли и СРАЗУ ЗАЛОЧИЛИ слот
        slot = slot_manager.suggest_and_lock(
            doctor_id=doctor["id"],
            date=session.collected_data["date"],
            call_id=session.call_id,
        )
        if not slot:
            return "На эту дату свободных слотов нет. Назовите другую дату."

        # 3. Запомнили в сессии — что предлагаем
        session.collected_data["proposed_slot"] = slot
        session.collected_data["doctor_id"] = doctor["id"]
        session.state = "CONFIRM_SLOT"

        return f"Есть свободное время {slot}. Подходит?"

    if session.state == "CONFIRM_SLOT":
        if is_yes(user_text):
            # 4. Пациент согласился — создаём запись в МИС
            mss_client.create_visit(
                client_id=session.collected_data["client_id"],
                doctor_id=session.collected_data["doctor_id"],
                visit_date=session.collected_data["proposed_slot"],
            )
            # 5. Лок можно снять — запись уже в МИС
            slot_manager.unlock(
                session.collected_data["doctor_id"],
                session.collected_data["proposed_slot"],
            )
            session.state = "BOOKING_DONE"
            return "Записали вас. Ждём в указанное время."

        elif is_no(user_text):
            # 6. Пациент отказался — снимаем лок, предлагаем другой слот
            slot_manager.unlock(
                session.collected_data["doctor_id"],
                session.collected_data["proposed_slot"],
            )
            new_slot = slot_manager.suggest_and_lock(
                doctor_id=session.collected_data["doctor_id"],
                date=session.collected_data["date"],
                call_id=session.call_id,
            )
            if not new_slot:
                session.state = "ASK_SPECIALTY"
                return "Больше слотов на эту дату нет. Назовите другую дату."

            session.collected_data["proposed_slot"] = new_slot
            return f"Тогда есть {new_slot}. Подходит?"