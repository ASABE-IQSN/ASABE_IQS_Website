from django.db import migrations


def populate_fks(apps, schema_editor):
    QuestionResponse = apps.get_model('compforms', 'QuestionResponse')
    FormQuestion = apps.get_model('compforms', 'FormQuestion')
    TeamQuestionAssignment = apps.get_model('compforms', 'TeamQuestionAssignment')

    unmatched = []

    qs = (
        QuestionResponse.objects
        .filter(form_question__isnull=True, team_assignment__isnull=True)
        .select_related(
            'form_response__event_form__form',
            'form_response__event_team',
        )
        .iterator(chunk_size=500)
    )

    for qr in qs:
        compform_id = qr.form_response.event_form.form_id
        question_id = qr.question_id
        event_team_id = qr.form_response.event_team_id

        # Flat question path
        fq = FormQuestion.objects.filter(
            form_id=compform_id, question_id=question_id
        ).first()
        if fq:
            qr.form_question_id = fq.pk
            qr.save(update_fields=['form_question_id'])
            continue

        # Group question path — look up via TeamQuestionAssignment.
        # A question can appear in multiple groups of the same form; if so we
        # take the first match. The old model had no group context on the answer
        # so we can't do better than this during migration.
        tqa = TeamQuestionAssignment.objects.filter(
            event_team_id=event_team_id,
            question_id=question_id,
            group__form_id=compform_id,
        ).first()
        if tqa:
            qr.team_assignment_id = tqa.pk
            qr.save(update_fields=['team_assignment_id'])
            continue

        unmatched.append(qr)

    # Empty-answer orphans (question removed from form) — safe to delete.
    # Non-empty orphans represent real data loss if dropped, so we raise instead.
    lossy = [qr.pk for qr in unmatched if qr.answer or qr.image]
    if lossy:
        raise Exception(
            f"Could not resolve {len(lossy)} QuestionResponse row(s) with non-empty answers. "
            f"PKs: {lossy} — investigate before re-running."
        )
    empty_pks = [qr.pk for qr in unmatched]
    if empty_pks:
        QuestionResponse.objects.filter(pk__in=empty_pks).delete()
        print(f"  Deleted {len(empty_pks)} orphaned empty-answer row(s): {empty_pks}")


def reverse_populate(apps, schema_editor):
    QuestionResponse = apps.get_model('compforms', 'QuestionResponse')
    QuestionResponse.objects.update(form_question=None, team_assignment=None)


class Migration(migrations.Migration):
    dependencies = [
        ('compforms', '0011_questionresponse_form_question_team_assignment'),
    ]

    operations = [
        migrations.RunPython(populate_fks, reverse_populate),
    ]
