CREATE DATABASE IF NOT EXISTS rastreador_solar
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE rastreador_solar;

CREATE TABLE IF NOT EXISTS dados_controle (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    erro      FLOAT          NOT NULL,
    saida     FLOAT          NOT NULL,
    p         FLOAT          NOT NULL,
    i         FLOAT          NOT NULL,
    d         FLOAT          NOT NULL,
    timestamp BIGINT         NOT NULL
);

CREATE TABLE IF NOT EXISTS dados_solares (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    valor_piranometro  FLOAT  NOT NULL,
    valor_fotodetector FLOAT  NOT NULL,
    referencia         FLOAT  NOT NULL,
    timestamp          BIGINT NOT NULL
);
