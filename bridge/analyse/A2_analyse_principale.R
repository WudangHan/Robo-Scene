# Plan d'analyse statistique A.2 v1.0 — analyse principale (modèle mixte, Kenward-Roger) et sensibilité ordinale.
# Script produit par la plateforme ROBO-SCÈNE (fonction Q-03) ; à exécuter par le chercheur dans le dossier
# d'analyse daté, à côté de scores_I7.csv et parametres.csv. Logiciels prévus par A.2 §7 : lme4, pbkrtest, ordinal.
#
#   Rscript A2_analyse_principale.R
#
# Codage : facteurs centrés (affichée = +0,5, non affichée = −0,5 ; robot = +0,5, voix et surtitres = −0,5),
# de sorte que chaque coefficient principal est la différence moyenne entre ses deux niveaux.

suppressPackageStartupMessages({ library(lme4); library(pbkrtest); library(ordinal) })

d <- read.csv2("scores_I7.csv", stringsAsFactors = FALSE, na.strings = c("NA", ""))
par <- read.csv2("parametres.csv", stringsAsFactors = FALSE)
exclues <- strsplit(par$representations_exclues[1], "\\|")[[1]]
exclues <- exclues[!is.na(exclues) & nzchar(exclues)]

d <- subset(d, presence_complete == 1 & !(id_representation %in% exclues))
d$prov <- ifelse(d$cond_provenance == "affichee", 0.5, -0.5)
d$supp <- ifelse(d$cond_support == "robot", 0.5, -0.5)
avec_support <- length(unique(d$supp)) > 1
f_droite <- if (avec_support) "prov * supp + (1 | id_representation)" else "prov + (1 | id_representation)"

test_kr <- function(m, nom) {
  b <- fixef(m); L <- matrix(0, 1, length(b)); L[1, which(names(b) == nom)] <- 1
  V <- as.matrix(vcovAdj(m)); se <- sqrt(drop(L %*% V %*% t(L)))
  ddf <- get_Lb_ddf(m, L)
  list(estimation = unname(b[nom]), erreur_type = se, ddl = ddf, t = unname(b[nom]) / se)
}

sortie <- list()

# H4a — agentivité perçue, différence entre conditions de provenance, bilatérale
m_ag <- lmer(as.formula(paste("SC_AG ~", f_droite)), data = d, REML = TRUE)
h4a <- test_kr(m_ag, "prov"); h4a$p <- 2 * pt(-abs(h4a$t), h4a$ddl)
sortie$H4a <- h4a

# H4b — engagement narratif, non-infériorité, borne −0,4 écart-type (écart-type individuel de SC_NE)
m_ne <- lmer(as.formula(paste("SC_NE ~", f_droite)), data = d, REML = TRUE)
delta <- 0.4 * sd(d$SC_NE, na.rm = TRUE)
h4b <- test_kr(m_ne, "prov"); h4b$borne <- -delta
h4b$t_ni <- (h4b$estimation + delta) / h4b$erreur_type
h4b$p <- pt(h4b$t_ni, h4b$ddl, lower.tail = FALSE)
sortie$H4b <- h4b
sortie$H4_soutenue <- (h4a$p < 0.05) && (h4b$p < 0.05)

# H2 — agentivité perçue, robot > texte, unilatérale (si le facteur « support » existe : D08)
if (avec_support) {
  h2 <- test_kr(m_ag, "supp"); h2$p <- pt(h2$t, h2$ddl, lower.tail = FALSE); sortie$H2 <- h2
}

# Sensibilité ordinale préenregistrée (A.2 §5.2) : modèle cumulatif à effets mixtes, énoncé par énoncé
items <- c(grep("^NE_", names(d), value = TRUE), paste0("AG_", 1:6))
f_ord <- if (avec_support) "prov * supp + (1 | id_representation)" else "prov + (1 | id_representation)"
ordinale <- lapply(items, function(it) {
  y <- d[[it]]
  if (all(is.na(y)) || length(unique(na.omit(y))) < 3) return(NULL)
  dd <- d; dd$y <- factor(y, ordered = TRUE)
  m <- try(clmm(as.formula(paste("y ~", f_ord)), data = dd), silent = TRUE)
  if (inherits(m, "try-error")) return(data.frame(enonce = it, estimation_prov = NA, p_prov = NA))
  s <- summary(m)$coefficients
  data.frame(enonce = it, estimation_prov = s["prov", "Estimate"], p_prov = s["prov", "Pr(>|z|)"])
})
ordinale <- do.call(rbind, ordinale)

capture.output({
  cat("Analyse principale A.2 — ", format(Sys.time()), "\n\n")
  str(sortie)
  cat("\nSensibilité ordinale (coefficient de provenance par énoncé ; AG_5 non recodé : signe inverse attendu)\n")
  print(ordinale)
  cat("\nsessionInfo()\n"); print(sessionInfo())
}, file = "resultats_R.txt")
write.csv2(ordinale, "sensibilite_ordinale.csv", row.names = FALSE)
cat("Résultats écrits dans resultats_R.txt et sensibilite_ordinale.csv\n")
