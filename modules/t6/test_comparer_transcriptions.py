from comparer_transcriptions import normaliser, wer


def test_normalisation():
    assert normaliser("Bon, ben… [rire] J’sais pas, euh, MOI !") == ["bon", "ben", "j'sais", "pas", "euh", "moi"]


def test_wer_valeurs_connues():
    ref = "le roi entre dans la salle"
    assert wer(ref, "le roi entre dans la salle") == 0
    assert wer(ref, "le roi rentre dans la salle") == round(1 / 6, 4)          # une substitution
    assert wer(ref, "le roi entre la salle") == round(1 / 6, 4)                # une suppression
    assert wer(ref, "le roi entre dans la grande salle") == round(1 / 6, 4)    # une insertion
