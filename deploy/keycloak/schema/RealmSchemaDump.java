import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;
import org.keycloak.representations.idm.ClientRepresentation;
import org.keycloak.representations.idm.ProtocolMapperRepresentation;
import org.keycloak.representations.idm.RealmRepresentation;
import org.keycloak.representations.idm.RoleRepresentation;
import org.keycloak.representations.idm.RolesRepresentation;
import org.keycloak.util.JsonSerialization;

import java.io.FileInputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

/**
 * Runs Keycloak's OWN realm deserializer over a realm file.
 *
 * Keycloak's realm import reads the file with
 * JsonSerialization.readValue(stream, RealmRepresentation.class), so this uses
 * the exact same static mapper and the exact same representation classes taken
 * from the keycloak-core artifact that matches the container image tag.
 *
 * Modes:
 *   parse <file>  deserialize the realm; exit 0 on success, 1 with the error
 *   props         emit the property names Jackson accepts, per class
 */
public class RealmSchemaDump {

    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("props")) {
            printProps();
            return;
        }
        String path = args.length > 1 ? args[1] : args[0];
        try (InputStream in = new FileInputStream(path)) {
            RealmRepresentation realm = JsonSerialization.readValue(in, RealmRepresentation.class);
            System.out.println("PARSE OK");
            System.out.println("realm=" + realm.getRealm());

            List<String> clientIds = new ArrayList<>();
            if (realm.getClients() != null) {
                for (ClientRepresentation c : realm.getClients()) {
                    clientIds.add(c.getClientId());
                }
            }
            System.out.println("clients=" + clientIds);

            RolesRepresentation roles = realm.getRoles();
            if (roles != null && roles.getRealm() != null) {
                List<String> names = new ArrayList<>();
                for (RoleRepresentation r : roles.getRealm()) {
                    names.add(r.getName());
                }
                System.out.println("realmRoles=" + names);
            }

            if (realm.getClients() != null) {
                for (ClientRepresentation c : realm.getClients()) {
                    System.out.println("client " + c.getClientId()
                            + " publicClient=" + c.isPublicClient()
                            + " standardFlow=" + c.isStandardFlowEnabled()
                            + " directAccessGrants=" + c.isDirectAccessGrantsEnabled()
                            + " implicitFlow=" + c.isImplicitFlowEnabled()
                            + " serviceAccounts=" + c.isServiceAccountsEnabled());
                    System.out.println("  redirectUris=" + c.getRedirectUris());
                    System.out.println("  webOrigins=" + c.getWebOrigins());
                    System.out.println("  attributes=" + c.getAttributes());
                    if (c.getProtocolMappers() != null) {
                        for (ProtocolMapperRepresentation m : c.getProtocolMappers()) {
                            System.out.println("  mapper " + m.getName()
                                    + " -> " + m.getProtocolMapper()
                                    + " " + m.getConfig());
                        }
                    }
                }
            }
        } catch (Exception e) {
            System.out.println("PARSE FAILED");
            System.out.println(e.getClass().getName());
            System.out.println(e.getMessage());
            System.exit(1);
        }
    }

    private static void printProps() throws Exception {
        printFor(RealmRepresentation.class, "RealmRepresentation");
        printFor(ClientRepresentation.class, "ClientRepresentation");
        printFor(ProtocolMapperRepresentation.class, "ProtocolMapperRepresentation");
        printFor(RolesRepresentation.class, "RolesRepresentation");
        printFor(RoleRepresentation.class, "RoleRepresentation");
    }

    /**
     * Ask Jackson directly which properties it accepts, by feeding it a field
     * that cannot exist and reading getKnownPropertyIds() off the resulting
     * exception. This is the very set the deserializer checks an incoming realm
     * file against, so it cannot drift from the accept/reject behaviour the way
     * a hand-derived list from reflection can.
     */
    private static void printFor(Class<?> type, String label) throws Exception {
        String probe = "__pios_probe_field_that_cannot_exist__";
        TreeSet<String> names = new TreeSet<>();
        try {
            JsonSerialization.mapper.readValue("{\"" + probe + "\": null}", type);
            throw new IllegalStateException(
                    label + " accepted an unknown field; it must not be validated this way");
        } catch (UnrecognizedPropertyException e) {
            for (Object id : e.getKnownPropertyIds()) {
                names.add(String.valueOf(id));
            }
        }
        System.out.println("### " + label);
        for (String n : names) {
            System.out.println(n);
        }
        System.out.println("### END");
    }
}
