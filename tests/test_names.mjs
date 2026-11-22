import assert from "node:assert/strict";
import test from "node:test";
import { findProfileQuery, searchDirectory } from "../static/js/names.js";

const mayor = {id: "mayor", name: "Χάρης Δούκας", party: "Αθήνα Τώρα"};
const councillor = {id: "councillor", name: "Γιάννης Δούκας", party: "Αθήνα Ψηλά"};
const another = {id: "another", name: "Μαρία Στρατηγάκη", party: "Αθήνα Τώρα"};
const people = [mayor, councillor, another];

test("profile and directory searches support Greek accents, inflections, and name order", () => {
    for (const query of ["ΧΑΡΗΣ ΔΟΥΚΑΣ", "Χάρη Δούκα", "Δούκας Χάρης"]) {
        assert.deepEqual(findProfileQuery(query, people), [mayor]);
        assert.deepEqual(searchDirectory(people, query), [mayor]);
    }
    assert.deepEqual(findProfileQuery("προφίλ του Χάρη Δούκα;", people), [mayor]);
    assert.deepEqual(searchDirectory(people, "ΑΘΗΝΑ ΤΩΡΑ"), [mayor, another]);
    assert.deepEqual(searchDirectory(people, "Στρατηγ"), [another]);
});

test("ambiguous surnames produce every match without choosing a profile", () => {
    assert.deepEqual(findProfileQuery("Δουκας", people), [mayor, councillor]);
    assert.deepEqual(searchDirectory(people, "Δουκας"), [mayor, councillor]);
    assert.deepEqual(findProfileQuery("προφίλ του Ανύπαρκτου Προσώπου", people), []);
});

test("civic questions stay in Q&A even when they contain a matching name", () => {
    for (const question of [
        "Τι πρότεινε ο Χάρης Δούκας για τα απορρίμματα;",
        "Χάρης Δούκας (τι είπε για την αποκομιδή;)",
        "Ποιος είναι υπεύθυνος για την αποκομιδή;",
    ]) {
        assert.equal(findProfileQuery(question, people), null);
    }
});

test("the demo profile can be found by its full name or a single name word", () => {
    const demo = {id: "demo-fictional-profile", name: "Hackathon Athens", status: "demo"};
    const roster = [...people, demo];
    assert.deepEqual(findProfileQuery("Hackathon Athens", roster), [demo]);
    assert.deepEqual(findProfileQuery("Hackathon", roster), [demo]);
    assert.deepEqual(searchDirectory(roster, "Hackathon"), [demo]);
    assert.equal(findProfileQuery("Τι είναι το Hackathon;", roster), null);
});
