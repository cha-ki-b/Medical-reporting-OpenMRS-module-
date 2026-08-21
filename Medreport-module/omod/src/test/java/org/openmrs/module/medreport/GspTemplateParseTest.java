package org.openmrs.module.medreport;

import groovy.text.SimpleTemplateEngine;
import org.junit.Test;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

/**
 * Compiles every {@code .gsp} through the same engine the UI Framework uses at runtime.
 *
 * <h3>Why this exists</h3>
 * A GSP is only compiled when a clinician opens the page. A template syntax error therefore
 * survives {@code mvn clean install}, ships, and surfaces as a full-page
 * "UI Framework Error" stack trace in front of a user - which is exactly what happened: the
 * imaging fragment used JSP-style {@code <%-- --%>} comments, which Groovy's
 * {@code SimpleTemplateEngine} does not support. It parsed {@code <%} and then choked on the
 * {@code --} that followed, producing
 * {@code expecting '}', found 'view' @ line 32, column 24}.
 *
 * <p>Nothing else in the build could have caught it. The brace-balance and message-key checks
 * in {@link ModuleWiringTest} are approximations of a parser; this is the parser.
 *
 * <p>{@code createTemplate} only <em>compiles</em> - it never runs the template - so no
 * OpenMRS context, model or {@code ui} object is needed. Undefined variables are resolved
 * dynamically at render time and are correctly not an error here.
 */
public class GspTemplateParseTest {

    private static final File WEBAPP =
            new File(new File("").getAbsoluteFile(), "src/main/webapp");

    private List<File> templates() {
        List<File> found = new ArrayList<File>();
        collect(new File(WEBAPP, "pages"), found);
        collect(new File(WEBAPP, "fragments"), found);
        assertFalse("no .gsp templates were found under " + WEBAPP, found.isEmpty());
        return found;
    }

    private void collect(File directory, List<File> into) {
        File[] children = directory.listFiles();
        if (children == null) {
            return;
        }
        for (File child : children) {
            if (child.isDirectory()) {
                collect(child, into);
            } else if (child.getName().endsWith(".gsp")) {
                into.add(child);
            }
        }
    }

    private String read(File file) throws IOException {
        StringBuilder text = new StringBuilder();
        Reader reader = new InputStreamReader(new FileInputStream(file), Charset.forName("UTF-8"));
        try {
            char[] chunk = new char[8192];
            int count;
            while ((count = reader.read(chunk)) != -1) {
                text.append(chunk, 0, count);
            }
        } finally {
            reader.close();
        }
        return text.toString();
    }

    @Test
    public void everyTemplateCompilesWithTheEngineTheUiFrameworkUses() throws Exception {
        Map<String, String> failures = new LinkedHashMap<String, String>();

        for (File template : templates()) {
            // A fresh engine per template: the compiler caches generated script classes, and
            // reusing one across files makes a failure report the wrong filename.
            SimpleTemplateEngine engine = new SimpleTemplateEngine();
            try {
                engine.createTemplate(read(template));
            } catch (Exception e) {
                String message = e.getMessage();
                failures.put(template.getName(),
                        message != null ? message.replace((char) 10, (char) 32).replace((char) 13, (char) 32).trim()
                                        : e.getClass().getName());
            }
        }

        if (!failures.isEmpty()) {
            StringBuilder report = new StringBuilder(
                    "GSP template(s) failed to compile - these would render as a "
                            + "'UI Framework Error' page to the user:\n");
            for (Map.Entry<String, String> failure : failures.entrySet()) {
                report.append("  - ").append(failure.getKey())
                      .append(": ").append(failure.getValue()).append('\n');
            }
            fail(report.toString());
        }
    }

    /**
     * Proves the test above is actually capable of failing. A parse check that silently stops
     * parsing is worse than no check, so the exact construct that caused the outage is
     * compiled here and required to be rejected.
     */
    @Test
    public void theParseCheckRejectsJspStyleComments() {
        String jspComment = "<div>\n<%-- this is JSP syntax, not Groovy --%>\n</div>";
        try {
            new SimpleTemplateEngine().createTemplate(jspComment);
            fail("SimpleTemplateEngine accepted <%-- --%>; this test can no longer detect "
                    + "the regression it exists for");
        } catch (Exception expected) {
            // Correct: Groovy has no JSP comment syntax.
        }
    }

    /** The supported form, for contrast - a Groovy block comment inside a scriptlet. */
    @Test
    public void groovyBlockCommentsInsideScriptletsAreAccepted() throws Exception {
        String groovyComment = "<div>\n<% /* this is the supported way to comment */ %>\n</div>";
        assertTrue(new SimpleTemplateEngine().createTemplate(groovyComment) != null);
    }
}
