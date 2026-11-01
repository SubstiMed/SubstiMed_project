<?php
// SubstiMed.app/config/bd.php

function getBD() 
{
    $chemin_db = __DIR__ . '/../../database/substimed.db';
    try {
        $pdo = new PDO('sqlite:' . $chemin_db);
        // Activation des erreurs sous forme d'exceptions
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        // Récupération par défaut sous forme de tableau associatif
        $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
        return $pdo;
    } catch (PDOException $e) {
        die("Erreur de connexion à la base de données : " . $e->getMessage());
    }
}